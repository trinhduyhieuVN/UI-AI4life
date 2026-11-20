"""Train and evaluate a causal DHGNN + EBM on whole trading sessions."""
import argparse
import copy
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parent
bundled = ROOT.parent / "work" / "mbo_pilot_deps"
if bundled.exists():
    sys.path.insert(0, str(bundled))
import numpy as np
import pandas as pd
import torch
from torch.nn import functional as F
from sklearn.metrics import (accuracy_score, average_precision_score, confusion_matrix,
                             f1_score, precision_score, recall_score, roc_auc_score)
from model import SessionEnergy

INPUTS = ("x","mask","edge","step","ctx")
SEED = 42


def load_sessions(directory, manifest):
    sessions = {}
    for row in manifest.itertuples():
        with np.load(directory/"sessions"/(row.day+".npz")) as archive:
            session = {k:archive[k] for k in (*INPUTS, "minute","timestamp")}
        minutes = session["minute"]
        if len(minutes)<60 or np.any(np.diff(minutes)<=0):
            raise ValueError(f"Invalid session {row.day}")
        sessions[row.day] = session
    return sessions


def standardize(sessions, training_days):
    stats = {}
    for k in ("x","step","ctx"):
        total = squares = 0.
        count = 0
        for day in training_days:
            v=sessions[day][k]
            v=(v[sessions[day]["mask"]] if k=="x" else v.reshape(-1,v.shape[-1])).astype(np.float64)
            count+=len(v)
            total+=v.sum(0)
            squares+=(v*v).sum(0)
        mean=total/count
        std=np.sqrt(np.maximum(0,squares/count-mean**2))
        stats[k+"_mean"]=mean.astype("float32")
        stats[k+"_std"]=np.where(std>1e-5,std,1).astype("float32")
        for data in sessions.values():
            data[k]=np.clip((data[k]-stats[k+"_mean"])/stats[k+"_std"],-10,10)
    return stats


def tensors(session, device):
    return {k:torch.from_numpy(session[k]).to(device) for k in INPUTS}


def pair(model, session, device, rng, duration=30, lag=None):
    """Delay complete order graph snapshots; keep flow, book summary and context on time."""
    batch=tensors(session,device)
    n=len(session["minute"])
    delay = int(rng.integers(1,6)) if lag is None else lag
    # Pick a contiguous interval with complete historical graph observations.
    ok=np.flatnonzero(session["minute"][duration+delay-1:]-session["minute"][:n-duration-delay+1]==duration+delay-1)
    if not len(ok): raise ValueError("No continuous interval for proxy")
    start=int(rng.choice(ok))+delay
    end=start+duration
    changed={k:(v[start-delay:end-delay] if k in ("x","mask","edge") else v[start:end])
             for k,v in batch.items()}
    emb=model.embed_minutes(batch)
    replacement=model.embed_minutes(changed)
    corrupted=torch.cat((emb[:start],replacement,emb[end:]))
    scores,_=model.trajectory(torch.stack((emb,corrupted)))
    return scores,start,end,delay


def objective(scores,end):
    i=sorted(set((end-1,(end-1+scores.shape[1]-1)//2,scores.shape[1]-1)))
    raw,synthetic=scores[:,i]
    return F.softplus(1+raw-synthetic).mean()+0.001*(raw.square()+synthetic.square()).mean()


def epoch(model, sessions, days, device, rng, optimizer=None):
    model.train(optimizer is not None)
    losses=[]
    with torch.set_grad_enabled(optimizer is not None):
        for day in days:
            if optimizer is not None: optimizer.zero_grad(set_to_none=True)
            scores,_,end,_=pair(model,sessions[day],device,rng)
            loss=objective(scores,end)
            if not torch.isfinite(loss): raise ValueError("Non-finite loss")
            if optimizer is not None:
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(),2)
                optimizer.step()
            losses.append(loss.item())
    return float(np.mean(losses))


@torch.inference_mode()
def calibrate(model,sessions,days,device):
    observations=[]
    for day in days:
        s=sessions[day]
        energy,_=model.trajectory(model.embed_minutes(tensors(s,device))[None])
        observations.append(pd.Series(energy[0].cpu().numpy(),index=s["minute"]))
    frame=pd.concat(observations,axis=1)
    cuts=frame.max(axis=1).sort_index()
    if cuts.isna().any() or frame.count(axis=1).min()<3:
        raise ValueError("Insufficient calibration coverage")
    return cuts


@torch.inference_mode()
def evaluate(model,sessions,days,device,cuts):
    rows,final=[],[]
    parity=0.
    for i,day in enumerate(days):
        s=sessions[day]
        energy,start,end,delay=pair(model,s,device,np.random.default_rng(2027+i))
        raw,alt=energy.cpu().numpy()
        threshold=cuts.loc[s["minute"]].to_numpy()
        # Compare online updates with the whole-session computation, using this day's minutes only.
        embedding=model.embed_minutes(tensors(s,device))[None]
        state=None
        for j in range(0,embedding.shape[1],13):
            online,state=model.trajectory(embedding[:,j:j+13],state)
            parity=max(parity,float(np.abs(online[0].cpu().numpy()-raw[j:j+13]).max()))
        flag=raw>threshold
        stamp=pd.to_datetime(s["timestamp"],utc=True).tz_convert("America/New_York")
        rows.append(pd.DataFrame(dict(day=day,elapsed_minutes=s["minute"]+1,window_end_ny=stamp,
                       observed_energy=raw,synthetic_energy=alt,threshold=threshold,observed_alert=flag,
                       injected=(np.arange(len(raw))>=start)&(np.arange(len(raw))<end))))
        final.append(dict(day=day,n_minutes=len(raw),observed_energy=raw[-1],synthetic_energy=alt[-1],
                          threshold=threshold[-1],observed_margin=raw[-1]-threshold[-1],
                          synthetic_margin=alt[-1]-threshold[-1],observed_alert=bool(flag[-1]),
                          synthetic_alert=bool(alt[-1]>threshold[-1]),observed_alert_minutes=int(flag.sum()),
                          first_observed_alert_end_ny=str(stamp[flag][0]) if flag.any() else "",
                          injection_start_minute=int(s["minute"][start]),delay_minutes=delay))
    if parity>1e-4: raise ValueError(f"Online/offline difference: {parity}")
    return pd.concat(rows,ignore_index=True),pd.DataFrame(final),parity


def proxy_metrics(table):
    labels=np.r_[np.zeros(len(table),int),np.ones(len(table),int)]
    score=np.r_[table.observed_margin,table.synthetic_margin]
    pred=(score>0).astype(int)
    tn,fp,fn,tp=confusion_matrix(labels,pred,labels=[0,1]).ravel()
    return dict(test_sessions=len(table),proxy_examples=len(labels),
                accuracy=accuracy_score(labels,pred),precision=precision_score(labels,pred,zero_division=0),
                recall=recall_score(labels,pred),f1=f1_score(labels,pred),
                roc_auc=roc_auc_score(labels,score),average_precision=average_precision_score(labels,score),
                paired_wins=int((table.synthetic_energy>table.observed_energy).sum()),
                tn=int(tn),fp=int(fp),fn=int(fn),tp=int(tp),
                observed_close_alerts=int(table.observed_alert.sum()))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out",type=Path,default=ROOT/"results")
    p.add_argument("--epochs",type=int,default=15)
    p.add_argument("--threads",type=int,default=4)
    args=p.parse_args()
    begin=time.perf_counter()
    torch.set_num_threads(args.threads)
    torch.manual_seed(SEED)
    rng=np.random.default_rng(SEED)
    device=torch.device("cuda" if torch.cuda.is_available() else "cpu")
    manifest=pd.read_csv(args.out/"sessions.csv").sort_values("day")
    groups={k:v.day.tolist() for k,v in manifest.groupby("split")}
    assert not manifest.day.duplicated().any()
    assert max(groups["train"])<min(groups["validation"])<=max(groups["validation"])<min(groups["calibration"])<=max(groups["calibration"])<min(groups["test"])
    data=load_sessions(args.out,manifest)
    stats=standardize(data,groups["train"])
    np.savez(args.out/"normalization.npz",**stats)
    model=SessionEnergy().to(device)
    optimizer=torch.optim.AdamW(model.parameters(),lr=5e-4,weight_decay=1e-4)
    best=float("inf")
    history=[]
    train_start=time.perf_counter()
    for e in range(1,args.epochs+1):
        train=epoch(model,data,rng.permutation(groups["train"]),device,rng,optimizer)
        validation=epoch(model,data,groups["validation"],device,np.random.default_rng(9107))
        history.append(dict(epoch=e,train_loss=train,validation_loss=validation))
        pd.DataFrame(history).to_csv(args.out/"history.csv",index=False)
        print(f"epoch {e}: train={train:.4f} validation={validation:.4f}",flush=True)
        if validation<best:
            best=validation
            selected=e
            state=copy.deepcopy(model.state_dict())
        if e-selected>=4: break
    training_seconds=time.perf_counter()-train_start
    model.load_state_dict(state)
    model.eval()
    torch.save(dict(model=state,hidden=48,selected_epoch=selected,training_symbol="MSFT",
                    seed=SEED,feature_version=1),args.out/"model.pt")
    cuts=calibrate(model,data,groups["calibration"],device)
    cuts.rename("threshold").rename_axis("zero_based_minute").to_csv(args.out/"thresholds.csv")
    curves,table,parity=evaluate(model,data,groups["test"],device,cuts)
    curves.to_csv(args.out/"test_intraday.csv",index=False)
    table.to_csv(args.out/"test_sessions.csv",index=False)
    result=dict(proxy_metrics=proxy_metrics(table),device=str(device),seed=SEED,hidden=48,
                torch_version=str(torch.__version__),epochs=len(history),selected_epoch=selected,
                training_with_validation_seconds=training_seconds,fit_and_evaluate_seconds=time.perf_counter()-begin,
                max_online_difference=parity,split_counts={k:len(v) for k,v in groups.items()},
                usable_minutes=int(manifest.usable.sum()),records=int(manifest.records.sum()))
    (args.out/"metrics.json").write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2),flush=True)


if __name__=="__main__":
    main()

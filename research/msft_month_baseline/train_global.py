"""Joint, end-to-end training on all eight symbols, with date-disjoint evaluation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import time

import numpy as np
import pandas as pd

from train import (torch, SessionEnergy, INPUTS, SEED, standardize, tensors, epoch,
                   calibrate, evaluate, proxy_metrics)
from features import SYMBOLS
from prepare import plan

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"global8"


class GlobalSessionEnergy(SessionEnergy):
    """Identical parameters/outputs, with normal autograd on machines with sufficient RAM."""
    def embed_minutes(self,batch,block=48):
        return torch.cat([self.minute({k:v[i:i+block] for k,v in batch.items()})
                          for i in range(0,len(batch["ctx"]),block)])


def stamp(day,symbol):
    return f"{day}_{symbol}"


def load_session(folder, day, symbol):
    path=folder/symbol/"sessions"/f"{day}.npz"
    with np.load(path) as f:
        item={k:f[k] for k in (*INPUTS,"minute","timestamp")}
    minutes=item["minute"]
    if len(minutes)<60 or not np.all(np.diff(minutes)>0):
        raise ValueError(f"Incomplete or unordered features at {path}")
    return item


def apply_stats(session,stats):
    for k in ("x","step","ctx"):
        session[k]=np.clip((session[k]-stats[k+"_mean"])/stats[k+"_std"],-10,10)
    return session


def atomic_save(payload,dest):
    tmp=dest.with_suffix(".tmp")
    torch.save(payload,tmp)
    os.replace(tmp,dest)


def fit(folder,epochs,threads):
    torch.set_num_threads(threads)
    torch.manual_seed(SEED)
    device=torch.device("cuda" if torch.cuda.is_available() else "cpu")
    data={}
    groups={"train":[],"validation":[]}
    signature=hashlib.sha256()
    for day,split in plan():
        if split not in groups: continue
        for symbol in sorted(SYMBOLS):
            key=stamp(day,symbol)
            source=folder/symbol/"sessions"/f"{day}.json"
            signature.update(key.encode()+source.read_bytes())
            data[key]=load_session(folder,day,symbol)
            groups[split].append(key)
    assert [len(groups[k]) for k in ("train","validation")]==[160,40]
    config_hash=signature.hexdigest()
    stats=standardize(data,groups["train"])
    np.savez(folder/"normalization.npz",**stats)
    model=GlobalSessionEnergy().to(device)
    opt=torch.optim.AdamW(model.parameters(),lr=5e-4,weight_decay=1e-4)
    best=float("inf")
    log=[]
    rng=np.random.default_rng(SEED)
    resume=folder/"resume.pt"
    if resume.exists():
        state=torch.load(resume,map_location=device,weights_only=True)
        if config_hash!=state["config_hash"]: raise ValueError("Data changed since checkpoint")
        model.load_state_dict(state["model"]); opt.load_state_dict(state["optimizer"])
        best=state["best"]
        log=state["history"]
        rng.bit_generator.state=state["numpy_rng"]
    for e in range(len(log)+1,epochs+1):
        start=time.perf_counter()
        tr=epoch(model,data,rng.permutation(groups["train"]),device,rng,opt)
        va=epoch(model,data,groups["validation"],device,np.random.default_rng(9107))
        log.append(dict(epoch=e,train_loss=tr,validation_loss=va,seconds=time.perf_counter()-start))
        if va<best:
            best=va
            atomic_save(dict(model=model.state_dict(),hidden=48,seed=SEED,selected_epoch=e,
                     training_symbols=sorted(SYMBOLS),feature_version=1,config_hash=config_hash),folder/"model.pt")
        atomic_save(dict(model=model.state_dict(),optimizer=opt.state_dict(),history=log,config_hash=config_hash,
                         best=best,numpy_rng=rng.bit_generator.state),resume)
        pd.DataFrame(log).to_csv(folder/"history.csv",index=False)
        print(f"Epoch {e}/{epochs}: train {tr:.4f}, validation {va:.4f}, {log[-1]['seconds']:.1f}s",flush=True)
    return device


@torch.inference_mode()
def case_study(model,folder,stats,cuts,device):
    rows=[]
    for d in (16,17,18,19,22,23):
        day=f"2021-03-{d}"
        s=apply_stats(load_session(folder,day,"VIAC"),stats)
        emb=model.embed_minutes(tensors(s,device))[None]
        values=model.trajectory(emb)[0][0].cpu().numpy()
        threshold=cuts.loc[s["minute"]].to_numpy()
        rows.append(pd.DataFrame(dict(day=day,elapsed_minutes=s["minute"]+1,
                end_ny=pd.to_datetime(s["timestamp"],utc=True).tz_convert("America/New_York"),
                energy=values,threshold=threshold,margin=values-threshold,alert=values>threshold)))
    curves=pd.concat(rows,ignore_index=True)
    curves.to_csv(folder/"viac_march_intraday.csv",index=False)
    report=[]
    for day,g in curves.groupby("day"):
        hits=g[g.alert]
        report.append(dict(day=day,close_energy=float(g.energy.iloc[-1]),threshold=float(g.threshold.iloc[-1]),
             close_margin=float(g.margin.iloc[-1]),close_alert=bool(g.alert.iloc[-1]),alert_minutes=len(hits),
             first_alert_end_ny=str(hits.end_ny.iloc[0]) if len(hits) else ""))
    pd.DataFrame(report).to_csv(folder/"viac_march_sessions.csv",index=False)
    return report[-1]


def evaluate_run(folder,device,epochs):
    ck=torch.load(folder/"model.pt",map_location=device,weights_only=True)
    model=GlobalSessionEnergy().to(device)
    model.load_state_dict(ck["model"]);model.eval()
    with np.load(folder/"normalization.npz") as f: stats=dict(f)
    dates=plan()
    cal={}
    for day,split in dates:
        if split!="calibration": continue
        for sym in sorted(SYMBOLS):
            cal[stamp(day,sym)]=apply_stats(load_session(folder,day,sym),stats)
    # Keep the original baseline's maximum-at-each-minute rule; now pool 40 calibration sessions.
    cuts=calibrate(model,cal,list(cal),device)
    cuts.rename("threshold").rename_axis("zero_based_minute").to_csv(folder/"thresholds.csv")
    # Like-for-like diagnostic for the previous MSFT-only experiment: identical five
    # calibration sessions and maximum rule, while retaining the newly fitted weights.
    msft_cuts=calibrate(model,cal,[key for key in cal if key.endswith("_MSFT")],device)
    del cal
    by_symbol=[]
    tables=[]
    paths=[]
    parity=0.
    for sym in sorted(SYMBOLS):
        data={str(d):apply_stats(load_session(folder,d,sym),stats) for d,s in dates if s=="test"}
        curves,table,err=evaluate(model,data,list(data),device,cuts)
        if sym=="MSFT":
            matched=table.copy()
            last=curves.groupby("day",sort=False).tail(1)
            matched["threshold"]=msft_cuts.loc[last.elapsed_minutes.to_numpy()-1].to_numpy()
            for kind in ("observed","synthetic"):
                matched[kind+"_margin"]=matched[kind+"_energy"]-matched.threshold
                matched[kind+"_alert"]=matched[kind+"_margin"]>0
            (folder/"matched_msft_metrics.json").write_text(json.dumps(proxy_metrics(matched),indent=2))
        by_symbol.append(dict(symbol=sym,**proxy_metrics(table)))
        curves.insert(0,"symbol",sym);table.insert(0,"symbol",sym)
        tables.append(table);paths.append(curves);parity=max(parity,err)
    tables=pd.concat(tables,ignore_index=True);paths=pd.concat(paths,ignore_index=True)
    pd.DataFrame(by_symbol).to_csv(folder/"metrics_by_symbol.csv",index=False)
    tables.to_csv(folder/"test_sessions.csv",index=False)
    paths.to_csv(folder/"test_intraday.csv",index=False)
    event=case_study(model,folder,stats,cuts,device)
    history=pd.read_csv(folder/"history.csv")
    result=dict(epochs_run=len(history),budget=epochs,chosen_epoch=ck["selected_epoch"],
         training_seconds=history.seconds.sum(),split_counts=dict(train=160,validation=40,calibration=40,test=96),
         observed_alert_minutes=int(paths.observed_alert.sum()),test_minutes=len(paths),
         observed_sessions_with_any_alert=int((tables.observed_alert_minutes>0).sum()),
         max_online_difference=parity,proxy_metrics=proxy_metrics(tables),event=event)
    (folder/"metrics.json").write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2),flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out",type=Path,default=OUT)
    p.add_argument("--epochs",type=int,default=24)
    p.add_argument("--threads",type=int,default=4)
    args=p.parse_args()
    device=fit(args.out,args.epochs,args.threads)
    evaluate_run(args.out,device,args.epochs)

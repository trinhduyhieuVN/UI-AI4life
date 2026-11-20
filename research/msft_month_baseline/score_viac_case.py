from pathlib import Path
import sys, json, tempfile, hashlib
from datetime import date, timedelta
from types import SimpleNamespace

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path.cwd()
sys.path.insert(0,str(ROOT/"msft_month_baseline"))
from train import torch, SessionEnergy, tensors
from features import session_arrays, preprocess, read_context
from prepare import verify_file
torch.set_num_threads(4)
baseline=ROOT/"msft_month_baseline"/"results"
out=ROOT/"outputs"/"VIAC_20210323_frozen_MSFT"
out.mkdir(exist_ok=True,parents=True)
ck=torch.load(baseline/"model.pt",map_location="cpu",weights_only=True)
assert ck["training_symbol"]=="MSFT"
model=SessionEnergy(ck["hidden"])
model.load_state_dict(ck["model"])
model.eval()
cuts=pd.read_csv(baseline/"thresholds.csv").set_index("zero_based_minute").threshold
with np.load(baseline/"normalization.npz") as f: stats=dict(f)
jobs={}
for m in Path("D:/DATA_AI4LIFE").glob("*/metadata.json"):
    q=json.loads(m.read_text(encoding="utf-8-sig"))["query"]
    if q["dataset"]=="XNAS.ITCH" and len(q["symbols"])==1:
        jobs[q["schema"],q["symbols"][0]]=m.parent
def file(folder,name):
    entries=json.loads((folder/"manifest.json").read_text(encoding="utf-8-sig"))["files"]
    entry=next(e for e in entries if e["filename"]==name)
    verify_file(folder/name,entry)
    return folder/name
context={}
for symbol in ("SPY","QQQ"):
    folder=jobs["ohlcv-1m",symbol]
    context[symbol]=read_context(file(folder,next(folder.glob("*.ohlcv-1m.dbn.zst")).name))
days=["2021-03-16","2021-03-17","2021-03-18","2021-03-19","2021-03-22","2021-03-23"]
frames=[]
with tempfile.TemporaryDirectory() as temp, torch.inference_mode():
    for d in days:
        day=date.fromisoformat(d)
        path=file(jobs["mbo","VIAC"],f"xnas-itch-{day:%Y%m%d}.mbo.dbn.zst")
        audit=preprocess(path,"VIAC",day,context,32,Path(temp))
        assert not set(audit["audit"]).difference(("snapshot_resets","source_resets","regular_records")), audit["audit"]
        data,ts,minute=session_arrays(SimpleNamespace(path=Path(temp)/f"{d}_VIAC.npz"))
        assert np.array_equal(minute,np.arange(390))
        for k in ("x","step","ctx"):
            data[k]=np.clip((data[k]-stats[k+"_mean"])/stats[k+"_std"],-10,10)
        batch=tensors(data,torch.device("cpu"))
        emb=model.embed_minutes(batch)
        score=model.trajectory(emb[None])[0].flatten().numpy()
        state=None
        replay=[]
        for i in range(390):
            val,state=model.trajectory(emb[None,i:i+1],state)
            replay.append(val.item())
        assert np.allclose(score,replay,atol=5e-6)
        thresh=cuts.loc[minute].to_numpy()
        frames.append(pd.DataFrame(dict(day=d,window_end_ny=pd.to_datetime(ts,utc=True).tz_convert("America/New_York"),
                       elapsed_minutes=minute+1,energy=score,threshold=thresh,margin=score-thresh,alert=score>thresh)))
        print(d,int((score>thresh).sum()),float(score[-1]-thresh[-1]),flush=True)
all_scores=pd.concat(frames,ignore_index=True)
event=frames[-1].reset_index(drop=True)
event.to_csv(out/"event_minutes.csv",index=False)
summary=[]
for df in frames:
    hit=df[df.alert]
    groups=(df.alert!=df.alert.shift()).cumsum()
    summary.append(dict(day=df.day.iloc[0],close_energy=df.energy.iloc[-1],close_threshold=df.threshold.iloc[-1],
                close_margin=df.margin.iloc[-1],alert_minutes=len(hit),first_alert=str(hit.window_end_ny.iloc[0]) if len(hit) else "",
                longest_alert_minutes=int(hit.groupby(groups).size().max()) if len(hit) else 0))
summary=pd.DataFrame(summary)
summary.to_csv(out/"comparison.csv",index=False)
key=(event.alert!=event.alert.shift()).cumsum()
spans=[]
for _,g in event[event.alert].groupby(key):
    spans.append(dict(start=str(g.window_end_ny.iloc[0]-pd.Timedelta(minutes=1)),end=str(g.window_end_ny.iloc[-1]),
                      minutes=len(g),peak_margin=g.margin.max()))
pd.DataFrame(spans,columns=["start","end","minutes","peak_margin"]).to_csv(out/"alert_intervals.csv",index=False)
fig,ax=plt.subplots(figsize=(10,4))
for df in frames[:-1]:
    ax.plot(df.elapsed_minutes,df.energy,color="#bdc7ca",alpha=.65,lw=.9,label="5 phiên VIAC liền trước" if df is frames[0] else None)
ax.plot(event.elapsed_minutes,event.energy,color="#135f78",label="VIAC ngày 23/03",lw=2)
ax.plot(event.elapsed_minutes,event.threshold,color="#a34e1d",label="Ngưỡng MSFT theo phút",lw=1)
ax.fill_between(event.elapsed_minutes,event.threshold,event.energy,where=event.alert,color="#ecb784",alpha=.5)
ax.set(xticks=[1,30,90,150,210,270,330,390],xticklabels=["09:31","10:00","11:00","12:00","13:00","14:00","15:00","16:00"],xlabel="Giờ New York",ylabel="Điểm năng lượng tích lũy",title="VIAC  |  23/03/2021")
ax.legend(frameon=False,fontsize=9); ax.spines[["top","right"]].set_visible(False);ax.grid(alpha=.14)
fig.tight_layout()
fig.savefig(out/"session.png",dpi=160)
print(summary.to_string(index=False))
print('peak margin',event.loc[event.margin.idxmax()].to_string())
print('top spans',sorted(spans,key=lambda s:-s["minutes"])[:3])

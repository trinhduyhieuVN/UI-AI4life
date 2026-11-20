"""Score a historical trading session using the frozen eight-symbol DHGNN + EBM."""
import argparse
from datetime import date
import json
from pathlib import Path
import re
import tempfile
from types import SimpleNamespace

import numpy as np
import pandas as pd
from features import HOLIDAYS, preprocess, read_context, session_arrays, session_bounds
from prepare import ERRORS, verify_file
from train_global import GlobalSessionEnergy, INPUTS, apply_stats, tensors, torch

ROOT = Path(__file__).resolve().parent


def raw_session(data, symbol, day):
    if not date(2020,10,1) <= day <= date(2021,4,30):
        raise ValueError("The raw reader uses the Oct 2020-Apr 2021 session calendar. For other dates supply --features with a correctly prepared session.")
    if day.weekday() >= 5 or str(day) in HOLIDAYS:
        raise ValueError(f"Market closed: {day}")
    opening, length = session_bounds(day)
    wanted = {("mbo", symbol), ("ohlcv-1m", "SPY"), ("ohlcv-1m", "QQQ")}
    jobs = {}
    for meta in data.glob("*/metadata.json"):
        q = json.loads(meta.read_text(encoding="utf-8-sig"))["query"]
        if q["dataset"] != "XNAS.ITCH" or len(q["symbols"]) != 1: continue
        key = q["schema"], q["symbols"][0]
        if key not in wanted or not (int(q["start"]) <= opening and int(q["end"]) >= opening+length*60*10**9): continue
        entries = json.loads((meta.parent/"manifest.json").read_text(encoding="utf-8-sig"))["files"]
        if key[0]=="mbo":
            entries=[f for f in entries if f["filename"]==f"xnas-itch-{day:%Y%m%d}.mbo.dbn.zst"]
        else:
            def covers(entry):
                m=re.fullmatch(r"xnas-itch-(\d{8})(?:-(\d{8}))?\.ohlcv-1m\.dbn\.zst",entry["filename"])
                return bool(m and m[1]<=day.strftime("%Y%m%d")<=(m[2] or m[1]))
            entries=[f for f in entries if covers(f)]
        for entry in entries:
            path=meta.parent/entry["filename"]
            if key in jobs and jobs[key][1]["hash"]!=entry["hash"]: raise ValueError(f"Conflicting inputs: {key}")
            jobs[key]=path,entry
    missing=wanted-jobs.keys()
    if missing: raise FileNotFoundError(f"{day}: missing {sorted(missing)} under {data}")
    for path,entry in jobs.values(): verify_file(path,entry)
    context={s:read_context(jobs["ohlcv-1m",s][0]) for s in ("SPY","QQQ")}
    with tempfile.TemporaryDirectory() as tmp:
        audit=preprocess(jobs["mbo",symbol][0],symbol,day,context,32,Path(tmp))
        if any(audit["audit"].get(k,0) for k in ERRORS): raise ValueError(f"Book audit failed: {audit}")
        return session_arrays(SimpleNamespace(path=Path(tmp)/f"{day}_{symbol}.npz"))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol",required=True)
    parser.add_argument("--date",type=date.fromisoformat,required=True)
    parser.add_argument("--data",type=Path,default=Path("D:/DATA_AI4LIFE"))
    parser.add_argument("--model-dir",type=Path,default=ROOT/"global8")
    parser.add_argument("--features",type=Path,help="Prepared daily NPZ in global8 session format")
    parser.add_argument("--out",type=Path,default=ROOT/"scored_sessions")
    args=parser.parse_args()
    symbol=args.symbol.strip().upper()
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9.\-]*",symbol): parser.error("Invalid ticker")
    day=args.date
    src=args.features or args.model_dir/symbol/"sessions"/f"{day}.npz"
    if args.features or src.exists():
        with np.load(src) as d:
            a={k:d[k] for k in INPUTS}; ts=d["timestamp"]; minute=d["minute"]
    else:
        a,ts,minute=raw_session(args.data,symbol,day)
    stamp=pd.to_datetime(ts,utc=True).tz_convert("America/New_York")
    start=pd.Timestamp(str(day)+" 09:30",tz="America/New_York")
    if not len(stamp) or not np.array_equal(stamp.asi8, (start+pd.to_timedelta(minute+1,unit="min")).as_unit(stamp.unit).asi8):
        raise ValueError("Timestamps do not match the requested session")
    if not np.array_equal(minute,np.arange(len(minute))) or len(minute) not in (210,390):
        raise ValueError("Incomplete session; a final session score requires full coverage")
    if date(2020,10,1)<=day<=date(2021,4,30) and len(minute)!=session_bounds(day)[1]:
        raise ValueError("Session length does not match calendar")
    torch.set_num_threads(4)
    checkpoint=torch.load(args.model_dir/"model.pt",map_location="cpu",weights_only=True)
    model=GlobalSessionEnergy(checkpoint["hidden"])
    model.load_state_dict(checkpoint["model"]);model.eval()
    with np.load(args.model_dir/"normalization.npz") as stats: apply_stats(a,stats)
    threshold=pd.read_csv(args.model_dir/"thresholds.csv").set_index("zero_based_minute").threshold.loc[minute].to_numpy()
    with torch.inference_mode():
        emb=model.embed_minutes(tensors(a,torch.device("cpu")))
        score=model.trajectory(emb[None])[0][0].numpy()
    if not np.isfinite(score).all(): raise ValueError("Non-finite score")
    alert=score>threshold
    out=args.out/symbol/str(day)
    out.mkdir(parents=True,exist_ok=True)
    pd.DataFrame(dict(symbol=symbol,day=str(day),window_end_ny=stamp,elapsed_minutes=minute+1,
                      energy=score,threshold=threshold,margin=score-threshold,alert=alert)).to_csv(out/"intraday.csv",index=False)
    result=dict(symbol=symbol,day=str(day),minutes=len(minute),close_energy=float(score[-1]),
                close_threshold=float(threshold[-1]),close_margin=float(score[-1]-threshold[-1]),
                close_alert=bool(alert[-1]),alert_minutes=int(alert.sum()),
                first_alert_end_ny=str(stamp[alert][0]) if alert.any() else None)
    (out/"summary.json").write_text(json.dumps(result,indent=2),encoding="utf8")
    print(json.dumps(result,indent=2))

if __name__=="__main__": main()

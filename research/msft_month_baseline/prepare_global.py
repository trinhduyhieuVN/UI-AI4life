"""Prepare one November per symbol and disjoint December evaluation dates."""
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import date
from pathlib import Path
import argparse
import json
import os
import shutil
import time
import pandas as pd
from prepare import build, plan, verify_file, load_context
from features import SYMBOLS

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"global8"

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--data",type=Path,default=Path("D:/DATA_AI4LIFE"))
    parser.add_argument("--workers",type=int,default=7)
    args=parser.parse_args()
    start=time.perf_counter()
    jobs={}
    for path in args.data.glob("*/metadata.json"):
        q=json.loads(path.read_text(encoding="utf-8-sig"))["query"]
        if q["dataset"]=="XNAS.ITCH" and len(q["symbols"])==1:
            key=q["schema"],q["symbols"][0]
            if key in jobs: raise ValueError(f"Duplicate job {key}")
            jobs[key]=(path.parent,{e["filename"]:e for e in json.loads((path.parent/"manifest.json").read_text(encoding="utf-8-sig"))["files"]})
    ctx,hashes={},[]
    for etf in ("SPY","QQQ"):
        folder,files=jobs["ohlcv-1m",etf]
        name,=[n for n in files if n.endswith(".dbn.zst")]
        ctx[etf]=folder/name
        hashes.append(verify_file(folder/name,files[name]))
    tasks=[]
    for day,split in plan()+[(date(2021,3,d),"event" if d==23 else "comparison") for d in (16,17,18,19,22,23)]:
        for symbol in sorted(SYMBOLS):
            if day.year==2021 and symbol!="VIAC": continue
            folder,entries=jobs["mbo",symbol]
            target=OUT/symbol
            (target/"sessions").mkdir(exist_ok=True,parents=True)
            name=f"xnas-itch-{day:%Y%m%d}.mbo.dbn.zst"
            if symbol=="MSFT":
                prev=ROOT/"results"/"sessions"
                cache=prev/f"{day}.json"
                if cache.exists():
                    record=json.loads(cache.read_text())
                    if record["source_hash"]==entries[name]["hash"].split(":")[1] and record["context_hash"]==",".join(hashes):
                        for source in (cache,cache.with_suffix(".npz")):
                            dest=target/"sessions"/source.name
                            if not dest.exists(): shutil.copy2(source,dest)
            tasks.append((day,split,folder/name,entries[name],",".join(hashes),target,symbol))
    rows=[]
    with ProcessPoolExecutor(max_workers=args.workers,initializer=load_context,initargs=(ctx,)) as pool:
        futures={pool.submit(build,job):job for job in tasks}
        for future in as_completed(futures):
            symbol=futures[future][-1]
            item=future.result()
            rows.append(dict(**item,symbol=symbol))
            if len(rows)%20==0: print(len(rows),"/",len(tasks),flush=True)
    manifest=pd.DataFrame(rows).sort_values(["day","symbol"])
    assert not manifest.duplicated(["day","symbol"]).any()
    assert manifest[manifest.split=="train"].groupby("symbol").size().eq(20).sum()==8
    manifest.to_csv(OUT/"sessions.csv",index=False)
    print(manifest.groupby("split").size(),flush=True)
    (OUT/"preparation.json").write_text(json.dumps({"wall_seconds":time.perf_counter()-start}))

if __name__=="__main__": main()

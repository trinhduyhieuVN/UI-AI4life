"""Build and audit MSFT session features. Run before train.py."""
import argparse
from concurrent.futures import ProcessPoolExecutor
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
import hashlib
import json
import os
import tempfile
import time

import numpy as np
import pandas as pd
from features import HOLIDAYS, read_context, preprocess, session_arrays

ROOT = Path(__file__).resolve().parent
DEFAULT_OUT = ROOT / "results"
LEVELS = ("train", "validation", "calibration", "test")
ERRORS = ("duplicate_add", "invalid_add", "unmatched_reduction", "over_reduction",
          "timestamp_regressions", "unexpected_action_or_price")


def plan():
    result = []
    day = date(2020, 11, 1)
    while day <= date(2020, 12, 31):
        if day.weekday() < 5 and str(day) not in HOLIDAYS:
            split = ("train" if day.month == 11 else "validation" if day.day <= 7
                     else "calibration" if day.day <= 14 else "test")
            result.append((day, split))
        day += timedelta(days=1)
    return result


def verify_file(path, entry):
    if path.stat().st_size != entry["size"]:
        raise IOError(f"Size mismatch: {path}")
    with path.open("rb") as stream:
        checksum = hashlib.file_digest(stream, "sha256").hexdigest()
    if "sha256:" + checksum != entry["hash"]:
        raise IOError(f"Checksum mismatch: {path}")
    return checksum


def load_context(paths):
    global context
    context = {symbol: read_context(path) for symbol, path in paths.items()}


def build(job):
    day, split, path, entry, context_hash, out, *extra = job
    symbol = extra[0] if extra else "MSFT"
    checksum = verify_file(path, entry)
    dst = out / "sessions" / (str(day) + ".npz")
    info = dst.with_suffix(".json")
    if dst.exists() and info.exists():
        cached = json.loads(info.read_text())
        if (cached["source_hash"], cached["context_hash"], cached["feature_version"], cached["bytes"]) == (
                checksum, context_hash, 1, dst.stat().st_size):
            return cached
    with tempfile.TemporaryDirectory(dir=out) as scratch:
        scratch = Path(scratch)
        audit = preprocess(path, symbol, day, context, 32, scratch)
        if any(audit["audit"].get(k, 0) for k in ERRORS):
            raise ValueError(f"Order-book audit {day}: {audit['audit']}")
        raw = scratch / f"{day}_{symbol}.npz"
        arrays, ts, minute = session_arrays(SimpleNamespace(path=raw))
        if not len(minute):
            raise ValueError(f"No usable minutes: {day}")
        with np.load(raw) as data:
            spread = data["book"][minute,:,1].mean(1)
            flow = data["flow_minute"][minute]
            depth = data["book"][minute,:,2:4].mean((1,2))
        with dst.with_suffix(".partial").open("wb") as stream:
            np.savez_compressed(stream, **arrays, timestamp=ts, minute=minute, spread=spread,
                                cancel_count=flow[:,2], trade_volume=flow[:,9], depth=depth)
        os.replace(dst.with_suffix(".partial"),dst)
        result = dict(day=str(day), split=split, minutes=audit["minutes"], usable=len(minute),
                      records=audit["audit"]["regular_records"], volume=audit["trade_qty"],
                      median_spread_bps=float(np.median(spread)), market_missing=audit["market_missing"],
                      valid_book_seconds=audit["valid_book_seconds"], source_hash=checksum,
                      context_hash=context_hash, bytes=dst.stat().st_size, feature_version=1)
        info.write_text(json.dumps(result,indent=2))
        return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data",type=Path,default=Path("D:/DATA_AI4LIFE"))
    parser.add_argument("--out",type=Path,default=DEFAULT_OUT)
    parser.add_argument("--workers",type=int,default=5)
    args=parser.parse_args()
    started=time.perf_counter()
    (args.out/"sessions").mkdir(exist_ok=True,parents=True)
    target={("mbo","MSFT"),("ohlcv-1m","SPY"),("ohlcv-1m","QQQ")}
    jobs={}
    for p in args.data.glob("*/metadata.json"):
        q=json.loads(p.read_text(encoding="utf-8-sig"))["query"]
        if q["dataset"]=="XNAS.ITCH" and len(q["symbols"])==1:
            key=(q["schema"],q["symbols"][0])
            if key in target:
                if key in jobs: raise ValueError(f"Ambiguous job: {key}")
                entries=json.loads((p.parent/"manifest.json").read_text(encoding="utf-8-sig"))["files"]
                jobs[key]=(p.parent,{f["filename"]:f for f in entries})
    paths,hashes={},[]
    for symbol in ("SPY","QQQ"):
        folder,manifest=jobs["ohlcv-1m",symbol]
        name,=[n for n in manifest if n.endswith(".dbn.zst")]
        paths[symbol]=folder/name
        hashes.append(verify_file(folder/name,manifest[name]))
    folder,manifest=jobs["mbo","MSFT"]
    tasks=[]
    for day,split in plan():
        name=f"xnas-itch-{day:%Y%m%d}.mbo.dbn.zst"
        tasks.append((day,split,folder/name,manifest[name],",".join(hashes),args.out))
    records=[]
    with ProcessPoolExecutor(max_workers=args.workers,initializer=load_context,initargs=(paths,)) as pool:
        for row in pool.map(build,tasks):
            records.append(row)
            print(row["day"],row["split"],row["usable"],flush=True)
    pd.DataFrame(records).to_csv(args.out/"sessions.csv",index=False)
    (args.out/"preparation_time.json").write_text(json.dumps({"wall_seconds":time.perf_counter()-started,"workers":args.workers}))


if __name__=="__main__":
    main()

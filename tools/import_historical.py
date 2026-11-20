"""Import real minute bars + frozen-model scores into a local replay database."""
import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile

import numpy as np
import pandas as pd
try:
    from compression import zstd
except ImportError:
    import zstandard as zstd

# Offsets from Databento DBN v1 MboMsg (56 bytes, little-endian).
MBO = np.dtype(dict(names=["length","rtype","event","price","qty","flags","action"],
                    formats=["u1","u1","<u8","<i8","<u4","u1","S1"],
                    offsets=[0,1,8,24,32,36,38],itemsize=56))


def trade_bars(path, first_ns, minutes):
    trades=[]
    with zstd.open(path,"rb") as stream:
        header=stream.read(8)
        if header[:4]!=b"DBN\x01": raise ValueError(f"Expected DBN v1: {path}")
        stream.read(int.from_bytes(header[4:],"little"))
        rest=b""
        while chunk:=stream.read(4*1024*1024):
            chunk=rest+chunk
            end=len(chunk)//56*56
            rows=np.frombuffer(chunk[:end],dtype=MBO)
            rest=chunk[end:]
            if not ((rows["length"]==14)&(rows["rtype"]==160)).all(): raise ValueError(path)
            rows=rows[(rows["action"]==b"T")&((rows["flags"]&32)==0)&(rows["price"]>0)&(rows["price"]<2**62)
                      &(rows["event"]>=first_ns)&(rows["event"]<first_ns+minutes*60_000_000_000)]
            if rows.size:
                trades.append(pd.DataFrame(dict(minute=((rows["event"]-first_ns)//60_000_000_000).astype(int)+1,
                             price=rows["price"]/1e9,size=rows["qty"])))
        if rest: raise ValueError(f"Truncated MBO: {path}")
    tape=pd.concat(trades,ignore_index=True)
    bars=tape.groupby("minute").agg(open=("price","first"),high=("price","max"),low=("price","min"),
                                   close=("price","last"),volume=("size","sum"))
    return bars


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data",type=Path,required=True)
    parser.add_argument("--model-results",type=Path,required=True)
    parser.add_argument("--output",type=Path,default=Path(__file__).resolve().parents[1]/"data"/"historical.db")
    args=parser.parse_args()
    r=args.model_results
    market={}
    for meta in args.data.glob("*/metadata.json"):
        q=json.loads(meta.read_text(encoding="utf-8-sig"))["query"]
        if q["dataset"]=="XNAS.ITCH" and q["schema"]=="mbo" and len(q["symbols"])==1:
            market.setdefault(q["symbols"][0],[]).append(meta.parent)
    lookup=pd.read_csv(r/"sessions.csv").set_index(["symbol","day"])
    test=pd.read_csv(r/"test_intraday.csv").rename(columns={"window_end_ny":"end_ny","observed_energy":"energy"})
    case=pd.read_csv(r/"viac_march_intraday.csv").assign(symbol="VIAC")
    keep=["symbol","day","elapsed_minutes","end_ny","energy","threshold"]
    scored=pd.concat([test[keep],case[keep]],ignore_index=True)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=args.output.parent) as tmp:
        staging=Path(tmp)/"historical.db"
        with closing(sqlite3.connect(staging)) as db:
            db.executescript("""
                CREATE TABLE sessions(symbol TEXT, day TEXT, minutes INTEGER, open_ms INTEGER,
                    PRIMARY KEY(symbol,day));
                CREATE TABLE points(symbol TEXT, day TEXT, minute INTEGER, end_ms INTEGER,
                    open REAL, high REAL, low REAL, close REAL, volume INTEGER, energy REAL, threshold REAL,
                    PRIMARY KEY(symbol, day, minute));
            """)
            for (sym,day),g in scored.groupby(["symbol","day"]):
                g=g.sort_values("elapsed_minutes")
                audit=lookup.loc[sym,day]
                mins=g.elapsed_minutes.to_numpy()
                ends=pd.to_datetime(g.end_ny,utc=True).astype("datetime64[ns, UTC]").astype("int64").to_numpy()
                if not np.array_equal(mins,np.arange(1,audit.minutes+1)) or not np.all(np.diff(ends)==60_000_000_000):
                    raise ValueError(f"Incomplete scores: {sym} {day}")
                if not np.isfinite(g[["energy","threshold"]]).all().all(): raise ValueError("Invalid model output")
                name=f"xnas-itch-{day.replace('-','')}.mbo.dbn.zst"
                paths=[p/name for p in market[sym] if (p/name).is_file()]
                path,=paths
                with path.open("rb") as f:
                    if hashlib.file_digest(f,"sha256").hexdigest()!=audit.source_hash: raise ValueError(path)
                start=int(ends[0])-60_000_000_000
                bars=trade_bars(path,start,len(mins)).reindex(mins)
                if int(bars.volume.sum())!=audit.volume: raise ValueError(f"Volume mismatch: {sym} {day}")
                db.execute("INSERT INTO sessions VALUES(?,?,?,?)",(sym,day,len(mins),start//1000000))
                for row,t,bar in zip(g.itertuples(),ends,bars.itertuples()):
                    db.execute("INSERT INTO points VALUES(?,?,?,?,?,?,?,?,?,?,?)",(sym,day,row.elapsed_minutes,
                               int(t)//1000000,bar.open,bar.high,bar.low,bar.close,
                               0 if pd.isna(bar.volume) else int(bar.volume),row.energy,row.threshold))
            db.commit()
            print(db.execute("SELECT COUNT(*),SUM(minutes) FROM sessions").fetchone(),flush=True)
        os.replace(staging,args.output)


if __name__=="__main__": main()

import json
from pathlib import Path

from sqlalchemy import insert, select

from . import auth
from .models import (
    Bar, OutboxRow, Prefs, SignalEvent, SymbolRow, TradingSession, User, now,
)


def load_manifest(db, path) -> dict:
    m = json.loads(Path(path).read_text(encoding="utf-8"))
    db.add_all(
        [SymbolRow(symbol=s["s"], name=s["n"], sector=s["sec"]) for s in m["symbols"]]
    )
    db.add_all([TradingSession(date=d, label=d) for d in m["sessions"]])
    db.flush()
    bar_rows = [
        {"symbol": sym, "session_date": d, "minute": i,
         "o": b["o"], "h": b["h"], "l": b["l"], "c": b["c"], "v": b["v"]}
        for sym, days in m["bars"].items()
        for d, arr in days.items()
        for i, b in enumerate(arr)
    ]
    db.execute(insert(Bar), bar_rows)
    sig_rows, out_rows = [], []
    for key, evs in m["signals"].items():
        _sym, date = key.split("|")
        for e in evs:
            sig_rows.append(
                SignalEvent(
                    id=e["id"], symbol=e["sym"], session_date=date, type=e["type"],
                    start_idx=e["startIdx"], end_idx=e["endIdx"], score=e["score"],
                    threshold=e["threshold"], alert=int(e["alert"]), reason=e["reason"],
                    label=e["label"], suppressed=int(e["suppressed"]),
                    suppressed_reason=e["suppressedReason"], outbox=e["outbox"],
                    quality=e["quality"], model=e["model"],
                    model_version=e["modelVersion"],
                    features_json=json.dumps(e["features"]), plain_vi=e["plain"],
                    source="demo",
                )
            )
            out_rows.append(
                {"event_id": e["id"],
                 "status": "suppressed" if e["suppressed"] else "pending",
                 "attempts": 0, "updated_at": now()}
            )
    db.add_all(sig_rows)
    db.flush()
    db.execute(insert(OutboxRow), out_rows)
    db.commit()
    return {
        "symbols": len(m["symbols"]), "sessions": len(m["sessions"]),
        "bars": len(bar_rows), "signals": len(sig_rows),
    }


def ensure_demo(db) -> None:
    if db.scalar(select(User).where(User.username == "demo")) is not None:
        return
    u = User(
        username="demo", email="demo@nasdaq.replay",
        password_hash=auth.hash_password("demo1234"), is_demo=1,
    )
    db.add(u)
    db.flush()
    db.add(Prefs(user_id=u.id, role="retail"))
    db.commit()
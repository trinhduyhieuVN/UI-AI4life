from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from ..models import Bar, TradingSession

TFS = {"1m": 1, "5m": 5, "15m": 15, "1h": 60, "1D": 0}


def _sess_utc_ms(date: str) -> int:
    y, m, d = (int(x) for x in date.split("-"))
    return int(datetime(y, m, d, 14, 30, tzinfo=timezone.utc).timestamp() * 1000)


def _m1(db: OrmSession, symbol: str, date: str) -> list[dict]:
    base = _sess_utc_ms(date)
    rows = db.scalars(
        select(Bar)
        .where(Bar.symbol == symbol, Bar.session_date == date)
        .order_by(Bar.minute)
    )
    return [
        {"t": base + r.minute * 60000, "o": r.o, "h": r.h, "l": r.l, "c": r.c, "v": r.v}
        for r in rows
    ]


def _aggregate(m1: list[dict], step: int) -> list[dict]:
    out = []
    for i in range(0, len(m1), step):
        chunk = m1[i:i + step]
        if not chunk:
            break
        out.append(
            {
                "t": chunk[0]["t"],
                "o": chunk[0]["o"],
                "h": max(x["h"] for x in chunk),
                "l": min(x["l"] for x in chunk),
                "c": chunk[-1]["c"],
                "v": sum(x["v"] for x in chunk),
            }
        )
    return out


def get_bars(db: OrmSession, symbol: str, date: str, tf: str) -> list[dict]:
    if tf == "1D":
        dates = db.scalars(
            select(TradingSession.date)
            .where(TradingSession.date <= date)
            .order_by(TradingSession.date)
        )
        out = []
        for d in dates:
            day = _aggregate(_m1(db, symbol, d), 390)
            if day:
                out.append({**day[0], "day": d})
        return out
    m1 = _m1(db, symbol, date)
    step = TFS[tf]
    return m1 if step == 1 else _aggregate(m1, step)
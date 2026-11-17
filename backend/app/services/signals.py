import json

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from ..models import SignalEvent, TradingSession
from .bars import TFS, _sess_utc_ms


def session_dates(db: OrmSession) -> list[str]:
    return list(db.scalars(select(TradingSession.date).order_by(TradingSession.date)))


def cursor_minute(tf: str, cursor: int) -> int:
    return 389 if tf == "1D" else min(389, cursor * TFS[tf] + TFS[tf] - 1)


def revealed_signals(db: OrmSession, symbols: list[str], si: int, tf: str, cursor: int) -> list[SignalEvent]:
    dates = session_dates(db)
    if tf == "1D":
        upto = min(cursor, si)
        q = select(SignalEvent).where(
            SignalEvent.symbol.in_(symbols),
            SignalEvent.session_date.in_(dates[:upto + 1]),
        )
    else:
        cm = cursor_minute(tf, cursor)
        q = select(SignalEvent).where(
            SignalEvent.symbol.in_(symbols),
            SignalEvent.session_date == dates[si],
            SignalEvent.end_idx <= cm,
        )
    evs = list(db.scalars(q))
    base = {d: _sess_utc_ms(d) for d in dates}
    evs.sort(key=lambda e: (-(base[e.session_date] + e.end_idx * 60000), e.symbol))
    return evs


def event_out(e: SignalEvent, si: int) -> dict:
    base = _sess_utc_ms(e.session_date)
    ord_ = e.id.rsplit("|E", 1)[1]
    return {
        "id": e.id, "sym": e.symbol, "si": si, "type": e.type,
        "startIdx": e.start_idx, "endIdx": e.end_idx,
        "tStart": base + e.start_idx * 60000,
        "tEnd": base + e.end_idx * 60000,
        "windowStart": base + (e.start_idx // 5) * 5 * 60000,
        "segmentId": f"{e.symbol}-{e.session_date}-S{ord_}" if e.type == "segment" else None,
        "score": e.score, "threshold": e.threshold, "alert": bool(e.alert),
        "reason": e.reason, "label": e.label, "suppressed": bool(e.suppressed),
        "suppressedReason": e.suppressed_reason, "outbox": e.outbox,
        "quality": e.quality, "model": e.model, "modelVersion": e.model_version,
        "features": json.loads(e.features_json), "plain": e.plain_vi,
    }
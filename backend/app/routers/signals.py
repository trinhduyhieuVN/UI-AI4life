import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from .. import auth
from ..db import get_db
from ..models import SymbolRow, User, WatchlistItem
from ..roles import caps_for
from ..services.bars import TFS
from ..services.signals import cursor_minute, event_out, revealed_signals, session_dates

router = APIRouter(prefix="/api/v1", tags=["signals"])

DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def select_for(db: OrmSession, u: User, symbol, date, tf, cursor, scope):
    if tf not in TFS:
        raise HTTPException(422, "Timeframe không hợp lệ")
    if not DATE_RE.fullmatch(date or ""):
        raise HTTPException(422, "Ngày phải dạng YYYY-MM-DD")
    if cursor < 0:
        raise HTTPException(422, "Cursor không âm")
    dates = session_dates(db)
    if date not in dates:
        raise HTTPException(404, "Không có phiên này")
    si = dates.index(date)
    caps = caps_for(u)
    if scope == "all":
        if caps.sigScope != "all":
            raise HTTPException(403, {"detail": "Chỉ vai trò giám sát được quét toàn bộ mã", "cap": "scope_all"})
        symbols = list(db.scalars(select(SymbolRow.symbol).order_by(SymbolRow.symbol)))
    elif scope == "watch":
        if caps.sigScope not in ("watch", "all"):
            raise HTTPException(403, {"detail": "Vai trò hiện tại chỉ xem tín hiệu theo mã", "cap": "scope_watch"})
        symbols = list(
            db.scalars(
                select(WatchlistItem.symbol)
                .where(WatchlistItem.user_id == u.id)
                .order_by(WatchlistItem.position)
            )
        )
    else:
        if not symbol:
            raise HTTPException(422, "Thiếu symbol hoặc scope")
        if db.get(SymbolRow, symbol) is None:
            raise HTTPException(404, "Không có mã này")
        symbols = [symbol]
    evs = revealed_signals(db, symbols, si, tf, cursor)
    if scope == "all":
        evs = evs[:60]
    return evs, si, dates


@router.get("/signals")
def signals(
    symbol: str | None = None,
    date: str = "",
    tf: str = "5m",
    cursor: int = 0,
    scope: str | None = None,
    u: User = Depends(auth.current_user),
    db: OrmSession = Depends(get_db),
):
    evs, si, dates = select_for(db, u, symbol, date, tf, cursor, scope)
    out = [event_out(e, dates.index(e.session_date)) for e in evs]
    return {"signals": out, "cursorMinute": cursor_minute(tf, cursor)}
import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from .. import auth
from ..db import get_db
from ..models import SymbolRow, TradingSession, User
from ..services.bars import TFS, get_bars

router = APIRouter(prefix="/api/v1", tags=["market"])

DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


@router.get("/symbols")
def symbols(u: User = Depends(auth.current_user), db: OrmSession = Depends(get_db)):
    rows = db.scalars(select(SymbolRow).order_by(SymbolRow.symbol))
    return {"symbols": [{"symbol": r.symbol, "name": r.name, "sector": r.sector} for r in rows]}


@router.get("/sessions")
def sessions(u: User = Depends(auth.current_user), db: OrmSession = Depends(get_db)):
    return {"sessions": list(db.scalars(select(TradingSession.date).order_by(TradingSession.date)))}


@router.get("/bars")
def bars(
    symbol: str,
    date: str,
    tf: str = "5m",
    u: User = Depends(auth.current_user),
    db: OrmSession = Depends(get_db),
):
    if tf not in TFS:
        raise HTTPException(422, "Timeframe không hợp lệ")
    if not DATE_RE.fullmatch(date):
        raise HTTPException(422, "Ngày phải dạng YYYY-MM-DD")
    if db.get(SymbolRow, symbol) is None:
        raise HTTPException(404, "Không có mã này")
    if tf != "1D" and db.get(TradingSession, date) is None:
        raise HTTPException(404, "Không có phiên này")
    return {"symbol": symbol, "date": date, "tf": tf, "bars": get_bars(db, symbol, date, tf)}
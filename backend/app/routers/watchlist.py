from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from .. import auth
from ..db import get_db
from ..models import SymbolRow, User, WatchlistItem

router = APIRouter(prefix="/api/v1/watchlist", tags=["watchlist"])


class AddIn(BaseModel):
    symbol: str


class OrderIn(BaseModel):
    symbols: list[str]


def _watch(db: OrmSession, u: User) -> list[str]:
    return list(
        db.scalars(
            select(WatchlistItem.symbol)
            .where(WatchlistItem.user_id == u.id)
            .order_by(WatchlistItem.position)
        )
    )


@router.get("")
def get_watchlist(u: User = Depends(auth.current_user), db: OrmSession = Depends(get_db)):
    return {"watch": _watch(db, u)}


@router.post("")
def add_symbol(body: AddIn, u: User = Depends(auth.require_cap("rail_rw")), db: OrmSession = Depends(get_db)):
    sym = body.symbol.upper()
    if db.get(SymbolRow, sym) is None:
        raise HTTPException(404, "Không có mã này")
    if db.get(WatchlistItem, {"user_id": u.id, "symbol": sym}) is not None:
        raise HTTPException(409, "Mã đã có trong watchlist")
    pos = max(
        (w.position for w in db.scalars(select(WatchlistItem).where(WatchlistItem.user_id == u.id))),
        default=-1,
    )
    db.add(WatchlistItem(user_id=u.id, symbol=sym, position=pos + 1))
    db.commit()
    return {"watch": _watch(db, u)}


@router.delete("/{symbol}")
def remove_symbol(symbol: str, u: User = Depends(auth.require_cap("rail_rw")), db: OrmSession = Depends(get_db)):
    row = db.get(WatchlistItem, {"user_id": u.id, "symbol": symbol.upper()})
    if row is None:
        raise HTTPException(404, "Mã không có trong watchlist")
    db.delete(row)
    db.commit()
    return {"watch": _watch(db, u)}


@router.put("/order")
def reorder(body: OrderIn, u: User = Depends(auth.require_cap("rail_rw")), db: OrmSession = Depends(get_db)):
    current = _watch(db, u)
    if sorted(body.symbols) != sorted(current):
        raise HTTPException(422, "Danh sách gửi phải đúng bộ mã hiện tại")
    rows = {
        w.symbol: w
        for w in db.scalars(select(WatchlistItem).where(WatchlistItem.user_id == u.id))
    }
    for i, sym in enumerate(body.symbols):
        rows[sym].position = i
    db.commit()
    return {"watch": _watch(db, u)}
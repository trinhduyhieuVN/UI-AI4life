import sqlite3
from contextlib import closing

from fastapi import APIRouter, Depends, HTTPException, Query
from .. import auth
from ..config import ROOT
from ..services import report_mail
from ..services.session_report import make_report

router = APIRouter(prefix="/api/v1/historical", dependencies=[Depends(auth.current_user)])
DATABASE = ROOT / "data" / "historical.db"


def connection():
    db = sqlite3.connect(DATABASE.resolve().as_uri() + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    return db


def session_report(day):
    if not DATABASE.exists():
        raise HTTPException(404, "Chưa nhập dữ liệu MBO")
    with closing(connection()) as db:
        try:
            return make_report(db, day)
        except ValueError as error:
            raise HTTPException(404, str(error)) from error


@router.get("/session-report")
def preview_report(day: str):
    return session_report(day)


@router.post("/session-closed")
def session_closed(day: str, through: int = Query(ge=1, le=390)):
    if not DATABASE.exists():
        raise HTTPException(404, "Chưa nhập dữ liệu MBO")
    with closing(connection()) as db:
        session = db.execute("SELECT MAX(minutes) FROM sessions WHERE day=?", (day,)).fetchone()
    if through != session[0]:
        raise HTTPException(409, "Phiên chưa kết thúc")
    report = session_report(day)
    return {"status": report_mail.enqueue(report)}


@router.get("/sessions")
def catalog():
    if not DATABASE.exists():
        return {"sessions": []}
    with closing(connection()) as db:
        rows = db.execute("SELECT symbol, day, minutes, open_ms FROM sessions ORDER BY symbol, day DESC")
        return {"sessions": [dict(row) for row in rows]}


@router.get("/bars")
def bars(symbol: str, day: str):
    if not DATABASE.exists():
        raise HTTPException(404, "Chưa nhập dữ liệu MBO")
    with closing(connection()) as db:
        rows = db.execute("""SELECT end_ms AS t, open AS o, high AS h, low AS l,
                             close AS c, volume AS v, minute FROM points
                             WHERE symbol=? AND day=? ORDER BY minute""", (symbol, day))
        return {"bars": [dict(row) for row in rows]}


@router.get("/points")
def points(symbol: str, day: str, through: int = Query(ge=0, le=390), after: int = Query(default=0, ge=0, le=390)):
    if through < after:
        raise HTTPException(422, "Thứ tự thời gian không hợp lệ")
    if not DATABASE.exists():
        raise HTTPException(404, "Chưa nhập dữ liệu MBO")
    with closing(connection()) as db:
        session = db.execute("SELECT minutes FROM sessions WHERE symbol=? AND day=?", (symbol, day)).fetchone()
        if not session or through > session["minutes"]:
            raise HTTPException(404, "Không có khoảng phát lại này")
        rows = db.execute("""
            SELECT minute,end_ms,open,high,low,close,volume,energy,threshold
            FROM points WHERE symbol=? AND day=? AND minute>? AND minute<=? ORDER BY minute
        """, (symbol, day, after, through))
        return {"points": [dict(row) for row in rows]}

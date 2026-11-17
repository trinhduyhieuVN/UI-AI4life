import csv
import io
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session as OrmSession

from .. import auth
from ..db import get_db
from ..models import SymbolRow, TradingSession, User
from ..roles import caps_for
from ..services.bars import TFS, get_bars
from ..services.signals import event_out, session_dates
from .signals import DATE_RE, select_for

router = APIRouter(prefix="/api/v1/export", tags=["export"])

SIG_COLS = ["symbol", "segment_id", "timestamp", "window_start", "score", "threshold", "alert", "reason", "suppressed_reason", "outbox", "quality"]


def _iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


def _csv_response(buf: io.StringIO, filename: str) -> Response:
    return Response(
        content=buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/signals.csv")
def signals_csv(
    request: Request,
    symbol: str | None = None,
    date: str = "",
    tf: str = "5m",
    cursor: int = 0,
    scope: str | None = None,
    u: User = Depends(auth.require_cap("sigCSV")),
    db: OrmSession = Depends(get_db),
):
    if caps_for(u).blind and request.query_params.get("blind") != "0":
        raise HTTPException(403, {"detail": "Đang bật chế độ ẩn điểm — tắt blind để xuất CSV", "cap": "blind"})
    evs, si, dates = select_for(db, u, symbol, date, tf, cursor, scope)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(SIG_COLS)
    for e in evs:
        o = event_out(e, dates.index(e.session_date))
        w.writerow([
            o["sym"], o["segmentId"] or "", _iso(o["tEnd"]), _iso(o["windowStart"]),
            o["score"], o["threshold"], int(o["alert"]), o["reason"],
            o["suppressedReason"] or "", o["outbox"], o["quality"],
        ])
    return _csv_response(buf, "signals.csv")


@router.get("/bars.csv")
def bars_csv(
    symbol: str,
    date: str,
    tf: str = "5m",
    u: User = Depends(auth.require_cap("csv")),
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
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["t", "o", "h", "l", "c", "v"])
    for b in get_bars(db, symbol, date, tf):
        w.writerow([b["t"], b["o"], b["h"], b["l"], b["c"], b["v"]])
    return _csv_response(buf, "bars.csv")
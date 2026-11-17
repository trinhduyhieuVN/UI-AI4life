import hashlib
import json
import re
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from .. import auth
from ..config import SETTINGS
from ..db import get_db
from ..roles import caps_for
from ..services.audit import log_audit
from ..models import (
    Prefs,
    Review,
    Session as SessionRow,
    SymbolRow,
    User,
    ViewRow,
    WatchlistItem,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

ROLE_IDS = {"observer", "retail", "institutional", "compliance", "regulator", "quant"}
DEFAULT_WATCH = ["AAPL", "NVDA", "MSFT", "TSLA", "AMZN", "META", "AVGO", "AMD"]
DEFAULT_VIEWS = [
    {"id": "v-tech", "name": "Công nghệ", "symbols": ["AAPL", "MSFT", "GOOGL", "META", "ADBE", "INTU"], "sort": "chg", "tf": "5m"},
    {"id": "v-semi", "name": "Bán dẫn", "symbols": ["NVDA", "AVGO", "AMD", "QCOM", "INTC"], "sort": "vol", "tf": "1m"},
    {"id": "v-def", "name": "Phòng thủ", "symbols": ["PEP", "COST", "AMGN", "HON", "SBUX", "TMUS"], "sort": "name", "tf": "1D"},
]
USERNAME_RE = re.compile(r"[a-z0-9_]{3,24}")


class RegisterIn(BaseModel):
    username: str
    password: str
    role: str = "retail"
    email: str = ""


class LoginIn(BaseModel):
    username: str
    password: str


def _user_payload(u: User, p: Prefs) -> dict:
    return {"username": u.username, "email": u.email, "role": p.role}


def _ensure_prefs(db: OrmSession, user: User, role: str = "retail") -> Prefs:
    p = db.get(Prefs, user.id)
    if p is None:
        p = Prefs(user_id=user.id, role=role, future=1)
        db.add(p)
        db.commit()
    return p


@router.post("/register")
def register(body: RegisterIn, db: OrmSession = Depends(get_db)):
    name = body.username.lower()
    if not USERNAME_RE.fullmatch(name):
        raise HTTPException(422, "Tên đăng nhập: 3–24 ký tự a-z, 0-9, _")
    if len(body.password) < 8:
        raise HTTPException(422, "Mật khẩu tối thiểu 8 ký tự")
    if body.role not in ROLE_IDS:
        raise HTTPException(422, "Vai trò không hợp lệ")
    if db.scalar(select(User).where(User.username == name)) is not None:
        raise HTTPException(409, "Tên đăng nhập đã tồn tại")
    u = User(
        username=name,
        email=body.email,
        password_hash=auth.hash_password(body.password),
    )
    db.add(u)
    db.flush()
    p = Prefs(user_id=u.id, role=body.role, future=1)
    db.add(p)
    for i, sym in enumerate(DEFAULT_WATCH):
        if db.get(SymbolRow, sym) is None:
            db.add(SymbolRow(symbol=sym))
        db.add(WatchlistItem(user_id=u.id, symbol=sym, position=i))
    for v in DEFAULT_VIEWS:
        db.add(ViewRow(user_id=u.id, name=v["name"], config_json=json.dumps(v, ensure_ascii=False)))
    db.commit()
    return {"user": _user_payload(u, p)}


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: OrmSession = Depends(get_db)):
    auth.login_guard(request.client.host if request.client else "unknown")
    u = db.scalar(select(User).where(User.username == body.username.lower()))
    if u is None or not auth.verify_password(body.password, u.password_hash):
        raise HTTPException(401, "Sai tên đăng nhập hoặc mật khẩu")
    if not u.password_hash.startswith("argon2id$"):
        u.password_hash = auth.hash_password(body.password)
    p = _ensure_prefs(db, u)
    log_audit(db, u.id, "login")
    token = auth.create_session(db, u, request.headers.get("user-agent", ""))
    response.set_cookie(
        SETTINGS.cookie_name,
        token,
        max_age=SETTINGS.session_days * 86400,
        httponly=True,
        samesite="lax",
        secure=SETTINGS.https,
        path="/",
    )
    return {"user": _user_payload(u, p)}


@router.post("/logout")
def logout(request: Request, response: Response, u: User = Depends(auth.current_user), db: OrmSession = Depends(get_db)):
    token = request.cookies.get(SETTINGS.cookie_name, "")
    row = db.scalar(
        select(SessionRow).where(
            SessionRow.token_hash == hashlib.sha256(token.encode()).hexdigest()
        )
    )
    if row is not None:
        db.delete(row)
    log_audit(db, u.id, "logout")
    db.commit()
    response.delete_cookie(SETTINGS.cookie_name, path="/")
    return {"ok": True}


@router.get("/me")
def me(u: User = Depends(auth.current_user), db: OrmSession = Depends(get_db)):
    p = _ensure_prefs(db, u)
    watch = [
        w.symbol
        for w in db.scalars(
            select(WatchlistItem).where(WatchlistItem.user_id == u.id).order_by(WatchlistItem.position)
        )
    ]
    views = [
        json.loads(v.config_json)
        for v in db.scalars(select(ViewRow).where(ViewRow.user_id == u.id).order_by(ViewRow.id))
    ]
    reviews = {
        r.event_id: {"label": r.label, "reviewer": r.reviewer_name, "at": r.at}
        for r in db.scalars(select(Review).where(Review.user_id == u.id))
    }
    prefs = {"role": p.role, "theme": p.theme, "future": bool(p.future)}
    prefs.update(json.loads(p.chart_json or "{}"))
    caps = asdict(caps_for(u))
    caps["audit"] = auth.CAP_CHECKS["audit"](caps_for(u))
    return {"user": _user_payload(u, p), "prefs": prefs, "caps": caps, "watch": watch, "views": views, "reviews": reviews}
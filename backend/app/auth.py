import hashlib
import secrets
import time
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from .config import SETTINGS
from .db import get_db
from .models import Session as SessionRow, User
from .roles import caps_for

_ph = PasswordHasher()
_rate: dict[str, list[float]] = {}


def hash_password(pw: str) -> str:
    return "argon2id$" + _ph.hash(pw)


def verify_password(pw: str, stored: str) -> bool:
    if stored.startswith("argon2id$"):
        try:
            return _ph.verify(stored[len("argon2id$"):], pw)
        except (VerificationError, InvalidHashError):
            return False
    if stored.startswith("pbkdf2$"):
        _, kdf, salt, h = stored.split("$", 3)
        return verify_legacy(pw, salt, h, kdf)
    return False


def verify_legacy(pw: str, salt_hex: str, hash_hex: str, kdf: str) -> bool:
    if kdf == "pbkdf2-sha256-150k":
        calc = hashlib.pbkdf2_hmac(
            "sha256", pw.encode(), bytes.fromhex(salt_hex), 150000, 32
        ).hex()
    elif kdf == "sha256-iter-fallback":
        data = (salt_hex + ":" + pw).encode()
        h = hashlib.sha256(data).digest()
        for _ in range(6000):
            h = hashlib.sha256(h + data).digest()
        calc = h.hex()
    else:
        return False
    return secrets.compare_digest(calc, hash_hex)


def create_session(db: OrmSession, user: User, ua: str = "") -> str:
    token = secrets.token_urlsafe(32)
    expires = (
        datetime.now(timezone.utc) + timedelta(days=SETTINGS.session_days)
    ).isoformat()
    db.add(
        SessionRow(
            token_hash=hashlib.sha256(token.encode()).hexdigest(),
            user_id=user.id,
            expires_at=expires,
            user_agent=ua,
        )
    )
    db.commit()
    return token


def current_user(request: Request, db: OrmSession = Depends(get_db)) -> User:
    token = request.cookies.get(SETTINGS.cookie_name)
    if not token:
        raise HTTPException(401, "Chưa đăng nhập")
    row = db.scalar(
        select(SessionRow).where(
            SessionRow.token_hash == hashlib.sha256(token.encode()).hexdigest()
        )
    )
    if row is None or datetime.fromisoformat(row.expires_at) <= datetime.now(
        timezone.utc
    ):
        raise HTTPException(401, "Phiên không hợp lệ hoặc đã hết hạn")
    user = db.get(User, row.user_id)
    if user is None:
        raise HTTPException(401, "Chưa đăng nhập")
    return user


def login_guard(ip: str) -> None:
    t = time.monotonic()
    hits = [x for x in _rate.get(ip, []) if t - x < 60]
    if len(hits) >= SETTINGS.login_rate:
        _rate[ip] = hits
        raise HTTPException(429, "Quá nhiều lần đăng nhập — thử lại sau 1 phút")
    hits.append(t)
    _rate[ip] = hits


CAP_CHECKS = {
    "rail_rw": lambda c: c.rail == "rw",
    "views": lambda c: c.views,
    "sigCSV": lambda c: c.sigCSV,
    "csv": lambda c: c.csv,
    "review": lambda c: c.review,
    "scope_all": lambda c: c.sigScope == "all",
    "audit": lambda c: c.id in ("compliance", "regulator"),
}


def require_cap(cap: str):
    check = CAP_CHECKS[cap]

    def dep(u: User = Depends(current_user)) -> User:
        if not check(caps_for(u)):
            raise HTTPException(
                403, {"detail": "Vai trò hiện tại không có quyền này", "cap": cap}
            )
        return u

    return dep
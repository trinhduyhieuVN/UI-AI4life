import hashlib
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from .. import auth
from ..db import get_db
from ..models import (
    ImportRecord, Prefs, Review, SymbolRow, User, ViewRow, WatchlistItem, now,
)
from ..roles import ROLES, caps_for
from ..services.audit import log_audit
from .auth import DEFAULT_VIEWS, DEFAULT_WATCH, USERNAME_RE
from .prefs import _clean_chart
from .reviews import LABELS

router = APIRouter(prefix="/api/v1/data", tags=["data"])

ROLE_IDS = set(ROLES)


def _require_data_manager(u: User) -> None:
    if not caps_for(u).dataManager:
        raise HTTPException(403, {"detail": "Vai trò hiện tại không quản lý dữ liệu", "cap": "dataManager"})


def _chart_from_flat(prefs: dict, current: dict) -> dict:
    raw = dict(current)
    for k in ("type", "tf", "spd", "glow", "sound"):
        if k in prefs:
            raw[k] = prefs[k]
    ov = dict(raw.get("overlays") or {})
    for k in ("ma1", "ma2", "vwap", "grid", "cross"):
        if k in prefs:
            ov[k] = prefs[k]
    raw["overlays"] = ov
    sl = dict(raw.get("sliders") or {})
    if "rate" in prefs:
        sl["rate"] = prefs["rate"]
    if "density" in prefs:
        sl["density"] = prefs["density"]
    if "volFrac" in prefs:
        sl["vol"] = prefs["volFrac"]
    raw["sliders"] = sl
    return raw


@router.get("/backup")
def backup(u: User = Depends(auth.current_user), db: OrmSession = Depends(get_db)):
    _require_data_manager(u)
    out = []
    for usr in db.scalars(select(User).order_by(User.id)):
        p = db.get(Prefs, usr.id)
        prefs = {
            "role": p.role if p else "retail",
            "theme": p.theme if p else "workbench",
            "future": bool(p.future) if p else True,
        }
        if p:
            prefs.update(json.loads(p.chart_json or "{}"))
        watch = list(
            db.scalars(
                select(WatchlistItem.symbol)
                .where(WatchlistItem.user_id == usr.id)
                .order_by(WatchlistItem.position)
            )
        )
        views = [
            json.loads(v.config_json)
            for v in db.scalars(select(ViewRow).where(ViewRow.user_id == usr.id).order_by(ViewRow.id))
        ]
        reviews = {
            r.event_id: {"label": r.label, "reviewer": r.reviewer_name, "at": r.at}
            for r in db.scalars(select(Review).where(Review.user_id == usr.id))
        }
        out.append(
            {"username": usr.username, "email": usr.email, "prefs": prefs, "watchlist": watch, "views": views, "reviews": reviews}
        )
    return {"app": "nasdaq-replay", "version": 2, "exportedAt": now(), "users": out}


@router.post("/import-backup")
async def import_backup(request: Request, u: User = Depends(auth.current_user), db: OrmSession = Depends(get_db)):
    _require_data_manager(u)
    raw = await request.body()
    try:
        pack = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(422, "File không phải JSON hợp lệ")
    if not isinstance(pack, dict) or pack.get("app") != "nasdaq-replay":
        raise HTTPException(422, "Không phải backup của ứng dụng này")
    users = (pack.get("db") or {}).get("users")
    if not isinstance(users, dict):
        raise HTTPException(422, "Backup thiếu mục users")
    checksum = hashlib.sha256(raw).hexdigest()
    imported = skipped = 0
    for acc in users.values():
        if not isinstance(acc, dict) or not all(isinstance(acc.get(k), str) for k in ("name", "salt", "hash")):
            skipped += 1
            continue
        name = acc["name"].lower()
        if not USERNAME_RE.fullmatch(name):
            skipped += 1
            continue
        kdf = acc.get("kdf") or "pbkdf2-sha256-150k"
        legacy = "pbkdf2$" + kdf + "$" + acc["salt"] + "$" + acc["hash"]
        prefs = acc.get("prefs") if isinstance(acc.get("prefs"), dict) else {}
        role = prefs.get("role") if prefs.get("role") in ROLE_IDS else "retail"
        caps = ROLES[role]
        user = db.scalar(select(User).where(User.username == name))
        if user is not None and db.scalar(
            select(ImportRecord).where(
                ImportRecord.user_id == user.id, ImportRecord.payload_checksum == checksum
            )
        ) is not None:
            skipped += 1
            continue
        if user is None:
            user = User(
                username=name,
                email=acc.get("email") if isinstance(acc.get("email"), str) else "",
                password_hash=legacy,
            )
            db.add(user)
            db.flush()
            db.add(Prefs(user_id=user.id, role=role, future=1))
            for i, sym in enumerate(DEFAULT_WATCH):
                if db.get(SymbolRow, sym) is None:
                    db.add(SymbolRow(symbol=sym))
                db.add(WatchlistItem(user_id=user.id, symbol=sym, position=i))
            for v in DEFAULT_VIEWS:
                db.add(ViewRow(user_id=user.id, name=v["name"], config_json=json.dumps(v, ensure_ascii=False)))
        else:
            if not user.password_hash.startswith("argon2id$"):
                user.password_hash = legacy
            if db.get(Prefs, user.id) is None:
                db.add(Prefs(user_id=user.id, future=1))
        db.flush()
        p = db.get(Prefs, user.id)
        p.role = role
        if isinstance(prefs.get("theme"), str):
            p.theme = prefs["theme"]
        if isinstance(prefs.get("future"), bool):
            p.future = int(prefs["future"])
        if caps.forceFuture:
            p.future = 1
        p.chart_json = json.dumps(
            _clean_chart(_chart_from_flat(prefs, json.loads(p.chart_json or "{}")), caps),
            ensure_ascii=False,
        )
        p.updated_at = now()
        watch = prefs.get("watch")
        if isinstance(watch, list):
            rows = list(db.scalars(select(WatchlistItem).where(WatchlistItem.user_id == user.id)))
            existing = {w.symbol for w in rows}
            pos = max((w.position for w in rows), default=-1)
            for sym in watch:
                if not isinstance(sym, str) or sym in existing or db.get(SymbolRow, sym) is None:
                    continue
                pos += 1
                db.add(WatchlistItem(user_id=user.id, symbol=sym, position=pos))
                existing.add(sym)
        views = prefs.get("views")
        if isinstance(views, list):
            names = {v.name for v in db.scalars(select(ViewRow).where(ViewRow.user_id == user.id))}
            for v in views:
                if isinstance(v, dict) and isinstance(v.get("name"), str) and v["name"] not in names:
                    db.add(ViewRow(user_id=user.id, name=v["name"], config_json=json.dumps(v, ensure_ascii=False)))
                    names.add(v["name"])
        reviews = prefs.get("reviews")
        if isinstance(reviews, dict):
            for eid, rv in reviews.items():
                if not isinstance(rv, dict) or rv.get("label") not in LABELS:
                    continue
                r = db.scalar(select(Review).where(Review.user_id == user.id, Review.event_id == eid))
                if r is None:
                    r = Review(user_id=user.id, event_id=eid, reviewer_name=rv.get("reviewer") or name)
                    db.add(r)
                r.label = rv["label"]
                r.at = rv.get("at") if isinstance(rv.get("at"), str) else now()
        db.add(ImportRecord(user_id=user.id, payload_checksum=checksum))
        imported += 1
    log_audit(db, u.id, "import_backup", {"imported": imported, "skipped": skipped, "checksum": checksum})
    db.commit()
    return {"imported": imported, "skipped": skipped, "checksum": checksum}
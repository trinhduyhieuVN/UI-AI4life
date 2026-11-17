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


def _hex_ok(s: str) -> bool:
    return bool(s) and len(s) % 2 == 0 and all(c in "0123456789abcdefABCDEF" for c in s)


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


@router.post("/restore")
async def restore(request: Request, u: User = Depends(auth.current_user), db: OrmSession = Depends(get_db)):
    _require_data_manager(u)
    raw = await request.body()
    try:
        pack = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(422, "File không phải JSON hợp lệ")
    if not isinstance(pack, dict) or pack.get("app") != "nasdaq-replay" or pack.get("version") != 2:
        raise HTTPException(422, "Không phải backup v2 của ứng dụng này")
    users = pack.get("users")
    if not isinstance(users, list):
        raise HTTPException(422, "Backup thiếu mục users")
    entry = next(
        (x for x in users if isinstance(x, dict) and isinstance(x.get("username"), str) and x["username"].lower() == u.username),
        None,
    )
    if entry is None:
        raise HTTPException(422, "Backup không chứa tài khoản hiện tại")
    prefs = entry.get("prefs") if isinstance(entry.get("prefs"), dict) else {}
    role = prefs.get("role") if prefs.get("role") in ROLE_IDS else "retail"
    caps = ROLES[role]
    p = db.get(Prefs, u.id)
    if p is None:
        p = Prefs(user_id=u.id)
        db.add(p)
        db.flush()
    old_role = p.role
    p.role = role
    if isinstance(prefs.get("theme"), str):
        p.theme = prefs["theme"]
    p.future = 1 if caps.forceFuture else int(bool(prefs.get("future", True)))
    ov = prefs.get("overlays") if isinstance(prefs.get("overlays"), dict) else {}
    sl = prefs.get("sliders") if isinstance(prefs.get("sliders"), dict) else {}
    chart = {
        "type": prefs.get("type"), "tf": prefs.get("tf"), "spd": prefs.get("spd"),
        "glow": prefs.get("glow"), "sound": prefs.get("sound"),
        "overlays": {k: ov[k] for k in ("ma1", "ma2", "vwap", "grid", "cross") if k in ov},
        "sliders": {k: sl[k] for k in ("rate", "density", "zoom", "vol") if k in sl},
    }
    p.chart_json = json.dumps(_clean_chart(chart, caps), ensure_ascii=False)
    p.updated_at = now()
    # SQLAlchemy xếp INSERT trước DELETE cùng bảng — flush deletes trước khi thêm hàng thay thế.
    for w in db.scalars(select(WatchlistItem).where(WatchlistItem.user_id == u.id)):
        db.delete(w)
    db.flush()
    syms = list(dict.fromkeys(
        s for s in (entry.get("watchlist") or []) if isinstance(s, str) and db.get(SymbolRow, s) is not None
    ))
    for i, sym in enumerate(syms):
        db.add(WatchlistItem(user_id=u.id, symbol=sym, position=i))
    for v in db.scalars(select(ViewRow).where(ViewRow.user_id == u.id)):
        db.delete(v)
    db.flush()
    views = []
    seen_names = set()
    for v in (entry.get("views") or []):
        if isinstance(v, dict) and isinstance(v.get("name"), str) and v["name"] not in seen_names:
            seen_names.add(v["name"])
            views.append(v)
    for v in views:
        db.add(ViewRow(user_id=u.id, name=v["name"], config_json=json.dumps(v, ensure_ascii=False)))
    for r in db.scalars(select(Review).where(Review.user_id == u.id)):
        db.delete(r)
    db.flush()
    reviews = entry.get("reviews") if isinstance(entry.get("reviews"), dict) else {}
    nrev = 0
    for eid, rv in reviews.items():
        if not isinstance(rv, dict) or rv.get("label") not in LABELS:
            continue
        db.add(Review(
            user_id=u.id, event_id=eid, label=rv["label"],
            reviewer_name=rv.get("reviewer") if isinstance(rv.get("reviewer"), str) else u.username,
            at=rv.get("at") if isinstance(rv.get("at"), str) else now(),
        ))
        nrev += 1
    if old_role != role:
        log_audit(db, u.id, "role_change", {"from": old_role, "to": role, "via": "restore"})
    log_audit(db, u.id, "restore_backup", {"watchlist": len(syms), "views": len(views), "reviews": nrev})
    db.commit()
    return {"restored": True, "watchlist": len(syms), "views": len(views), "reviews": nrev}


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
        if not isinstance(kdf, str) or kdf not in auth.LEGACY_KDFS or not _hex_ok(acc["salt"]) or not _hex_ok(acc["hash"]):
            skipped += 1
            continue
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
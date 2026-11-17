import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session as OrmSession

from .. import auth
from ..db import get_db
from ..models import AuditLog, Prefs, User, now
from ..roles import ROLES, RoleCaps

router = APIRouter(prefix="/api/v1/prefs", tags=["prefs"])

ROLE_IDS = set(ROLES)


class PrefsIn(BaseModel):
    role: str | None = None
    theme: str | None = None
    chart: dict | None = None
    future: bool | None = None


def _num(v, default):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else default


def _clean_chart(raw: dict, caps: RoleCaps) -> dict:
    t = raw.get("type")
    tf = raw.get("tf")
    ov = raw.get("overlays") or {}
    sl = raw.get("sliders") or {}
    return {
        "type": t if t in caps.types else caps.types[0],
        "tf": tf if tf in caps.tfs else caps.tfs[0],
        "spd": max(0, min(int(_num(raw.get("spd"), 1)), caps.maxSpd)),
        "overlays": {
            "ma1": max(2, min(200, int(_num(ov.get("ma1"), 9)))),
            "ma2": max(2, min(200, int(_num(ov.get("ma2"), 21)))),
            "vwap": bool(ov.get("vwap", True)),
            "grid": bool(ov.get("grid", True)),
            "cross": bool(ov.get("cross", True)),
        },
        "sliders": {
            "rate": max(0.2, min(12, _num(sl.get("rate"), 2))),
            "density": max(20, min(100, _num(sl.get("density"), 70))),
            "zoom": max(14, min(390, _num(sl.get("zoom"), 90))),
            "vol": max(0, min(46, _num(sl.get("vol"), 26))),
        },
        "theme": raw.get("theme") if isinstance(raw.get("theme"), str) else "workbench",
        "glow": max(0, min(100, int(_num(raw.get("glow"), 30)))),
        "sound": bool(raw.get("sound", True)),
    }


def _payload(p: Prefs) -> dict:
    return {
        "role": p.role,
        "theme": p.theme,
        "future": bool(p.future),
        "chart": json.loads(p.chart_json or "{}"),
    }


def _prefs_of(db: OrmSession, u: User) -> Prefs:
    p = db.get(Prefs, u.id)
    if p is None:
        p = Prefs(user_id=u.id, future=1)
        db.add(p)
        db.commit()
    return p


@router.get("")
def get_prefs(u: User = Depends(auth.current_user), db: OrmSession = Depends(get_db)):
    return _payload(_prefs_of(db, u))


@router.put("")
def put_prefs(body: PrefsIn, u: User = Depends(auth.current_user), db: OrmSession = Depends(get_db)):
    p = _prefs_of(db, u)
    new_role = body.role if body.role is not None else p.role
    if new_role not in ROLE_IDS:
        raise HTTPException(422, "Vai trò không hợp lệ")
    caps = ROLES[new_role]
    if body.future is False and caps.forceFuture:
        raise HTTPException(
            409, {"detail": "Vai trò này bắt buộc khoá nhìn trước tương lai", "cap": "forceFuture"}
        )
    if new_role != p.role:
        db.add(
            AuditLog(
                user_id=u.id,
                action="role_change",
                detail_json=json.dumps({"from": p.role, "to": new_role}),
            )
        )
        p.role = new_role
    if body.theme is not None:
        p.theme = body.theme
    if body.future is not None:
        p.future = int(body.future)
    if caps.forceFuture:
        p.future = 1
    raw_chart = body.chart if body.chart is not None else json.loads(p.chart_json or "{}")
    p.chart_json = json.dumps(_clean_chart(raw_chart, caps), ensure_ascii=False)
    p.updated_at = now()
    db.commit()
    return _payload(p)
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from .. import auth
from ..db import get_db
from ..models import User, ViewRow

router = APIRouter(prefix="/api/v1/views", tags=["views"])


class ViewIn(BaseModel):
    name: str
    config: dict


class ViewPatch(BaseModel):
    name: str | None = None
    config: dict | None = None


def _payload(v: ViewRow) -> dict:
    return {"id": v.id, "name": v.name, "config": json.loads(v.config_json)}


def _own(db: OrmSession, u: User, vid: int) -> ViewRow:
    v = db.get(ViewRow, vid)
    if v is None or v.user_id != u.id:
        raise HTTPException(404, "Không có view này")
    return v


@router.get("")
def list_views(u: User = Depends(auth.require_cap("views")), db: OrmSession = Depends(get_db)):
    rows = db.scalars(select(ViewRow).where(ViewRow.user_id == u.id).order_by(ViewRow.id))
    return {"views": [_payload(v) for v in rows]}


@router.post("")
def create_view(body: ViewIn, u: User = Depends(auth.require_cap("views")), db: OrmSession = Depends(get_db)):
    v = ViewRow(user_id=u.id, name=body.name, config_json=json.dumps(body.config, ensure_ascii=False))
    db.add(v)
    db.commit()
    return _payload(v)


@router.put("/{vid}")
def update_view(vid: int, body: ViewPatch, u: User = Depends(auth.require_cap("views")), db: OrmSession = Depends(get_db)):
    v = _own(db, u, vid)
    if body.name is not None:
        v.name = body.name
    if body.config is not None:
        v.config_json = json.dumps(body.config, ensure_ascii=False)
    db.commit()
    return _payload(v)


@router.delete("/{vid}")
def delete_view(vid: int, u: User = Depends(auth.require_cap("views")), db: OrmSession = Depends(get_db)):
    v = _own(db, u, vid)
    db.delete(v)
    db.commit()
    return {"ok": True}
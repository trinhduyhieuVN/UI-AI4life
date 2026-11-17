import json

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from .. import auth
from ..db import get_db
from ..models import AuditLog, User

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])


@router.get("")
def list_audit(u: User = Depends(auth.require_cap("audit")), db: OrmSession = Depends(get_db)):
    rows = db.execute(
        select(AuditLog, User.username)
        .outerjoin(User, AuditLog.user_id == User.id)
        .order_by(AuditLog.id.desc())
        .limit(200)
    ).all()
    return {
        "audit": [
            {"id": a.id, "username": un, "action": a.action, "detail": json.loads(a.detail_json), "at": a.at}
            for a, un in rows
        ]
    }
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from .. import auth
from ..db import get_db
from ..models import Review, SignalEvent, User, now
from ..services.audit import log_audit

router = APIRouter(prefix="/api/v1/reviews", tags=["reviews"])

LABELS = {"noteworthy", "ordinary", "uncertain", "data_error"}


class ReviewIn(BaseModel):
    event_id: str
    label: str


@router.get("")
def list_reviews(u: User = Depends(auth.current_user), db: OrmSession = Depends(get_db)):
    rows = db.scalars(select(Review).where(Review.user_id == u.id))
    return {
        "reviews": {
            r.event_id: {"label": r.label, "reviewer": r.reviewer_name, "at": r.at}
            for r in rows
        }
    }


@router.post("")
def save_review(body: ReviewIn, u: User = Depends(auth.require_cap("review")), db: OrmSession = Depends(get_db)):
    if body.label not in LABELS:
        raise HTTPException(422, "Nhãn rà soát không hợp lệ")
    if db.get(SignalEvent, body.event_id) is None:
        raise HTTPException(404, "Không có sự kiện này")
    r = db.scalar(
        select(Review).where(Review.user_id == u.id, Review.event_id == body.event_id)
    )
    if r is None:
        r = Review(user_id=u.id, event_id=body.event_id, reviewer_name=u.username)
        db.add(r)
    r.label = body.label
    r.reviewer_name = u.username
    r.at = now()
    log_audit(db, u.id, "review", {"event_id": body.event_id, "label": body.label})
    db.commit()
    return {"review": {"event_id": r.event_id, "label": r.label, "reviewer": r.reviewer_name, "at": r.at}}
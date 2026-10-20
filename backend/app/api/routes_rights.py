import uuid
from datetime import datetime
from typing import Literal
from datetime import timedelta, timezone
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.deps import require_role
from app.audit import audit
from app.core.crypto import encrypt
from app.core.db import get_db
from app.core.errors import AppError
from app.models import ContentRight, Episode, Movie, Season, TvSeries, User

router = APIRouter(prefix="/admin/rights")
creator = require_role("rights_admin", "content_admin", "super_admin")
approver = require_role("rights_admin", "super_admin")  # content admins cannot self-approve (separation of duties)


class RightIn(BaseModel):
    content_kind: Literal["movie", "episode"]
    content_id: uuid.UUID
    license_type: str = Field(min_length=2, max_length=64)
    proof_ref: str = Field(min_length=3, max_length=500)  # evidence reference, stored encrypted
    commercial_allowed: bool = False
    telegram_allowed: bool = False
    web_allowed: bool = False
    territories: list[str] = Field(min_length=1)
    valid_from: datetime
    valid_until: datetime

    @model_validator(mode="after")
    def window(self):
        if self.valid_until <= self.valid_from:
            raise ValueError("valid_until must be after valid_from")
        return self


@router.post("", status_code=201)
def create_right(body: RightIn, admin: User = Depends(creator), db: Session = Depends(get_db)):
    model = Movie if body.content_kind == "movie" else Episode
    if db.get(model, body.content_id) is None:
        raise AppError(404, "NOT_FOUND", "Target does not exist.")
    r = ContentRight(id=uuid.uuid4(), **body.model_dump(exclude={"proof_ref"}), proof_ref_encrypted=encrypt(body.proof_ref),
                     review_status="PENDING")
    db.add(r)
    audit(db, admin.id, "rights.create", body.content_kind, body.content_id, {"right_id": str(r.id)})
    db.commit()
    return {"id": r.id, "review_status": r.review_status}


def _set(db: Session, rid: uuid.UUID, admin: User, status: str, allowed_from: set[str]):
    r = db.get(ContentRight, rid)
    if r is None:
        raise AppError(404, "NOT_FOUND", "Not found.")
    if r.review_status not in allowed_from:
        raise AppError(409, "INVALID_TRANSITION", f"Cannot move rights from {r.review_status} to {status}.")
    r.review_status, r.reviewed_by = status, admin.id
    audit(db, admin.id, f"rights.{status.lower()}", r.content_kind, r.content_id, {"right_id": str(r.id)})
    db.commit()
    return {"id": r.id, "review_status": r.review_status}


@router.post("/{rid}/approve")
def approve(rid: uuid.UUID, admin: User = Depends(approver), db: Session = Depends(get_db)):
    return _set(db, rid, admin, "APPROVED", {"PENDING"})


@router.post("/{rid}/revoke")
def revoke(rid: uuid.UUID, admin: User = Depends(approver), db: Session = Depends(get_db)):
    return _set(db, rid, admin, "REVOKED", {"APPROVED", "PENDING"})  # takedown: effective on next delivery check


@router.get("")
def list_rights(status: str | None = None, expiring_days: int | None = Query(None, ge=1, le=365),
                cursor: int = Query(0, ge=0), limit: int = Query(30, ge=1, le=100),
                admin: User = Depends(creator), db: Session = Depends(get_db)):
    """Proof references are never returned."""
    from datetime import datetime
    now = datetime.now(timezone.utc)
    q = select(ContentRight)
    if status:
        q = q.where(ContentRight.review_status == status)
    if expiring_days:
        q = q.where(ContentRight.review_status == "APPROVED", ContentRight.valid_until >= now,
                    ContentRight.valid_until <= now + timedelta(days=expiring_days))
    rows = list(db.scalars(q.order_by(ContentRight.valid_until, ContentRight.id).offset(cursor).limit(limit + 1)))

    def label(r):
        if r.content_kind == "movie":
            m = db.get(Movie, r.content_id); return m.original_title if m else "?"
        row = db.execute(select(TvSeries.original_title, Season.season_number, Episode.episode_number)
                         .join(Season, Season.series_id == TvSeries.id).join(Episode, Episode.season_id == Season.id)
                         .where(Episode.id == r.content_id)).first()
        return f"{row[0]} S{row[1]:02d}E{row[2]:02d}" if row else "?"
    return {"items": [{"id": r.id, "content_kind": r.content_kind, "content_id": r.content_id, "label": label(r),
                       "license_type": r.license_type, "review_status": r.review_status, "valid_from": r.valid_from,
                       "valid_until": r.valid_until, "telegram_allowed": r.telegram_allowed, "web_allowed": r.web_allowed,
                       "commercial_allowed": r.commercial_allowed} for r in rows[:limit]],
            "next_cursor": str(cursor + limit) if len(rows) > limit else None}

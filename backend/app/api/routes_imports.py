import uuid
from typing import Literal
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.api.deps import require_role
from app.audit import audit
from app.core.config import get_settings
from app.core.crypto import decrypt, encrypt
from app.core.db import get_db
from app.core.errors import AppError
from app.imports.ssrf import UnsafeURL, validate_source_url
from app.imports.state import transition
from app.models import Episode, ImportJob, Movie, User
from app.rights import has_valid_rights

router = APIRouter(prefix="/admin/import-jobs")
staff = require_role("content_admin", "super_admin")


class JobIn(BaseModel):
    source_type: Literal["direct_url", "google_drive", "manual_upload"]
    source_ref: str = Field(min_length=8, max_length=2000)
    idempotency_key: str = Field(min_length=8, max_length=100)


class ApproveIn(BaseModel):
    candidate_kind: Literal["movie", "episode"]
    target_id: uuid.UUID


def out(j: ImportJob) -> dict:  # never includes the source reference
    return {"id": j.id, "status": j.status, "source_type": j.source_type, "candidate_kind": j.candidate_kind,
            "target_id": j.target_id, "progress_percent": j.progress_percent, "attempts": j.attempts,
            "error_code": j.error_code, "error_message_safe": j.error_message_safe, "lease_owner": j.lease_owner,
            "created_at": j.created_at, "requires_review": j.status == "NEEDS_REVIEW"}


def _job(db: Session, jid: uuid.UUID) -> ImportJob:
    j = db.get(ImportJob, jid)
    if j is None:
        raise AppError(404, "NOT_FOUND", "Not found.")
    return j


@router.post("", status_code=201)
def create(body: JobIn, admin: User = Depends(staff), db: Session = Depends(get_db)):
    if body.source_type != "direct_url":  # drive/upload need their own authorized-access flows
        raise AppError(422, "SOURCE_TYPE_NOT_SUPPORTED", "Only direct_url imports are supported yet.")
    try:
        validate_source_url(body.source_ref, get_settings().import_hosts)
    except UnsafeURL as e:
        raise AppError(422, "UNSAFE_SOURCE", f"Source rejected ({e}).")
    existing = db.scalar(select(ImportJob).where(ImportJob.idempotency_key == body.idempotency_key))
    if existing:
        if existing.requested_by == admin.id and decrypt(existing.source_ref_encrypted) == body.source_ref:
            return out(existing)  # idempotent replay
        raise AppError(409, "IDEMPOTENCY_CONFLICT", "Idempotency key already used for a different request.")
    j = ImportJob(id=uuid.uuid4(), source_type=body.source_type, source_ref_encrypted=encrypt(body.source_ref),
                  requested_by=admin.id, status="PENDING", idempotency_key=body.idempotency_key)
    db.add(j)
    transition(j, "NEEDS_REVIEW")  # AI/TMDB matching (Milestone 3) is not built: a human picks the target
    audit(db, admin.id, "import.create", "import_job", j.id, {"source_type": body.source_type})
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AppError(409, "IDEMPOTENCY_CONFLICT", "Duplicate request.")
    return out(j)


@router.get("")
def list_jobs(status: str | None = None, cursor: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100),
              admin: User = Depends(staff), db: Session = Depends(get_db)):
    q = select(ImportJob)
    if status:
        q = q.where(ImportJob.status == status)
    rows = list(db.scalars(q.order_by(ImportJob.created_at.desc(), ImportJob.id).offset(cursor).limit(limit + 1)))
    return {"items": [out(j) for j in rows[:limit]], "next_cursor": str(cursor + limit) if len(rows) > limit else None}


@router.get("/{jid}")
def get(jid: uuid.UUID, admin: User = Depends(staff), db: Session = Depends(get_db)):
    return out(_job(db, jid))


@router.post("/{jid}/approve")
def approve(jid: uuid.UUID, body: ApproveIn, admin: User = Depends(staff), db: Session = Depends(get_db)):
    j = _job(db, jid)
    model = Movie if body.candidate_kind == "movie" else Episode
    if db.get(model, body.target_id) is None:
        raise AppError(404, "NOT_FOUND", "Target does not exist.")
    if not has_valid_rights(db, body.candidate_kind, body.target_id):
        raise AppError(409, "RIGHTS_NOT_APPROVED", "The target needs an approved, in-window rights record first.")
    transition(j, "READY")
    j.candidate_kind, j.target_id = body.candidate_kind, body.target_id
    audit(db, admin.id, "import.approve", "import_job", j.id, {"kind": body.candidate_kind, "target": str(body.target_id)})
    db.commit()
    return out(j)


@router.post("/{jid}/retry")
def retry(jid: uuid.UUID, admin: User = Depends(staff), db: Session = Depends(get_db)):
    j = _job(db, jid)
    if j.status == "FAILED":
        transition(j, "READY"); j.attempts = 0
    elif j.status in ("BLOCKED_RIGHTS", "EXPIRED_SOURCE"):
        transition(j, "NEEDS_REVIEW")
    else:
        raise AppError(409, "INVALID_TRANSITION", f"Cannot retry a job in {j.status}.")
    j.error_code = j.error_message_safe = None
    audit(db, admin.id, "import.retry", "import_job", j.id)
    db.commit()
    return out(j)


@router.post("/{jid}/cancel")
def cancel(jid: uuid.UUID, admin: User = Depends(staff), db: Session = Depends(get_db)):
    j = _job(db, jid)
    transition(j, "CANCELLED")
    audit(db, admin.id, "import.cancel", "import_job", j.id)
    db.commit()
    return out(j)

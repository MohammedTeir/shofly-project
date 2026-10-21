import uuid
from datetime import timedelta
from typing import Literal
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.deps import worker_auth
from app.audit import audit
from app.core.config import get_settings
from app.core.crypto import encrypt
from app.core.db import get_db
from app.core.errors import AppError
from app.imports.service import claim_next, claim_payload, owned_job, to_retry_or_fail, utcnow
from app.imports.state import transition
from app.models import MediaAsset
from app.rights import has_valid_rights

router = APIRouter(prefix="/worker", dependencies=[Depends(worker_auth)])
Owner = Field(min_length=3, max_length=64)


class ClaimIn(BaseModel):
    worker_id: str = Owner


class OwnerIn(BaseModel):
    lease_owner: str = Owner


class ProgressIn(OwnerIn):
    status: Literal["DOWNLOADING", "PROBING", "PROCESSING", "UPLOADING", "VERIFYING"]
    progress_percent: int = Field(ge=0, le=100)


class CompleteIn(OwnerIn):
    verified: bool
    provider: str = Field(min_length=2, max_length=32)
    provider_ref: str = Field(min_length=1, max_length=500)
    segment_refs: list[str] = Field(default_factory=list, max_length=500)
    size_bytes: int = Field(gt=0)
    checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    duration_sec: int | None = Field(None, gt=0)
    quality: str | None = Field(None, max_length=32)
    codec: str | None = Field(None, max_length=32)
    audio_language: str | None = Field(None, max_length=32)
    edition: str | None = Field(None, max_length=32)


class FailIn(OwnerIn):
    error_code: str = Field(pattern=r"^[A-Z_]{3,40}$")
    error_message_safe: str | None = Field(None, max_length=300)
    retryable: bool = True


@router.get("/ping")
def ping():
    return {"ok": True}


@router.post("/jobs/claim")
def claim(body: ClaimIn, db: Session = Depends(get_db)):
    job = claim_next(db, body.worker_id)
    return {"job": claim_payload(job) if job else None}


@router.post("/jobs/{jid}/heartbeat")
def heartbeat(jid: uuid.UUID, body: OwnerIn, db: Session = Depends(get_db)):
    job = owned_job(db, jid, body.lease_owner)
    job.lease_until = utcnow() + timedelta(seconds=get_settings().job_lease_seconds)
    db.commit()
    return {"lease_until": job.lease_until}


@router.post("/jobs/{jid}/progress")
def progress(jid: uuid.UUID, body: ProgressIn, db: Session = Depends(get_db)):
    job = owned_job(db, jid, body.lease_owner)
    if body.status != job.status:
        transition(job, body.status)
    job.progress_percent = body.progress_percent
    db.commit()
    return {"status": job.status}


@router.post("/jobs/{jid}/complete")
def complete(jid: uuid.UUID, body: CompleteIn, db: Session = Depends(get_db)):
    job = owned_job(db, jid, body.lease_owner)
    if job.status != "VERIFYING":
        raise AppError(409, "INVALID_STATE", "Job must be in VERIFYING before completion.")
    if not body.verified:
        raise AppError(409, "NOT_VERIFIED", "Provider verification receipt is required.")
    if not has_valid_rights(db, job.candidate_kind, job.target_id):
        transition(job, "BLOCKED_RIGHTS")
        job.error_code, job.error_message_safe = "RIGHTS_NOT_APPROVED", "Rights missing, expired or revoked."
        db.commit()
        raise AppError(409, "BLOCKED_RIGHTS", "Rights are not valid; the asset was not attached.")
    if any(not ref or len(ref) > 500 for ref in body.segment_refs):
        raise AppError(400, "INVALID_SEGMENTS", "Invalid segment references.")
    if body.segment_refs and body.segment_refs[0] != body.provider_ref:
        raise AppError(400, "INVALID_SEGMENTS", "First segment must match primary reference.")
    col = MediaAsset.movie_id if job.candidate_kind == "movie" else MediaAsset.episode_id
    dup = db.scalar(select(MediaAsset).where(col == job.target_id, MediaAsset.checksum_sha256 == body.checksum_sha256))
    if dup:  # same bytes already attached to this target: never create a second asset
        asset, duplicate = dup, True
    else:
        asset = MediaAsset(id=uuid.uuid4(), import_job_id=job.id, provider=body.provider,
                           provider_ref_encrypted=encrypt(body.provider_ref),
                           segment_refs_encrypted=[encrypt(ref) for ref in body.segment_refs] if body.segment_refs else None,
                           size_bytes=body.size_bytes,
                           checksum_sha256=body.checksum_sha256, duration_sec=body.duration_sec, quality=body.quality,
                           codec=body.codec, audio_language=body.audio_language, edition=body.edition,
                           upload_status="verified", visibility="private",
                           **({"movie_id": job.target_id} if job.candidate_kind == "movie" else {"episode_id": job.target_id}))
        db.add(asset); duplicate = False
    transition(job, "COMPLETED")
    job.progress_percent = 100
    audit(db, None, "import.complete", "import_job", job.id, {"asset_id": str(asset.id), "duplicate": duplicate})
    db.commit()
    return {"asset_id": asset.id, "duplicate": duplicate}


@router.post("/jobs/{jid}/fail")
def fail(jid: uuid.UUID, body: FailIn, db: Session = Depends(get_db)):
    job = owned_job(db, jid, body.lease_owner)
    to_retry_or_fail(job, body.error_code, body.error_message_safe, body.retryable)
    db.commit()
    return {"status": job.status}

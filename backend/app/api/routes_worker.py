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
from app.core.crypto import encrypt, decrypt
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
    error_code: str = Field(pattern=r"^[A-Z0-9_]{3,40}$")
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
    dup = db.scalar(select(MediaAsset).where(col == job.target_id,
                      MediaAsset.checksum_sha256 == body.checksum_sha256).with_for_update())
    if dup and dup.upload_status in ("inactive", "cleanup_pending", "cleanup_failed"):
        # Same bytes but a fresh Telegram upload: replace the stale storage reference
        # atomically, preserving the unique checksum constraint and the asset ID.
        # Reject a replacement while another worker is actively deleting the old message.
        old_ref = dup.provider_ref_encrypted
        old_segments = dup.segment_refs_encrypted
        dup.provider = body.provider
        dup.provider_ref_encrypted = encrypt(body.provider_ref)
        dup.segment_refs_encrypted = [encrypt(ref) for ref in body.segment_refs] if body.segment_refs else None
        dup.import_job_id = job.id
        dup.size_bytes = body.size_bytes
        dup.duration_sec = body.duration_sec
        dup.quality = body.quality
        dup.codec = body.codec
        dup.audio_language = body.audio_language
        dup.edition = body.edition
        dup.upload_status = "verified"
        asset, duplicate = dup, False
        audit(db, None, "media.reupload_replaced", "media_asset", dup.id,
              {"previous_status": "inactive_or_pending", "old_storage_cleanup": "not_performed"})
    elif dup:
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


class CleanupResultIn(BaseModel):
    success: bool
    error_code: str | None = Field(None, pattern=r"^[A-Z0-9_]{3,40}$")


@router.post("/cleanup/claim")
def claim_cleanup(db: Session = Depends(get_db)):
    """Claim one pending asset; encrypted storage references never reach the dashboard."""
    asset = db.scalar(select(MediaAsset).where(MediaAsset.upload_status == "cleanup_pending",
                 MediaAsset.provider == "telegram").order_by(MediaAsset.created_at)
                 .with_for_update(skip_locked=True).limit(1))
    if asset is None:
        return {"asset": None}
    # Never delete the last playable copy of a movie/episode.
    col = MediaAsset.movie_id if asset.movie_id else MediaAsset.episode_id
    target = asset.movie_id or asset.episode_id
    replacement = db.scalar(select(MediaAsset.id).where(
        col == target, MediaAsset.id != asset.id,
        MediaAsset.upload_status == "verified").limit(1))
    if replacement is None:
        asset.upload_status = "inactive"
        audit(db, None, "media.cleanup_blocked_last_copy", "media_asset", asset.id)
        db.commit()
        return {"asset": None, "blocked": True, "reason": "LAST_COPY"}
    refs = [decrypt(asset.provider_ref_encrypted)]
    refs += [decrypt(ref) for ref in (asset.segment_refs_encrypted or [])]
    # Refuse to delete any message referenced by a different asset.
    messages = {(ref.split(":", 2)[0], ref.split(":", 2)[1]) for ref in refs}
    for other in db.scalars(select(MediaAsset).where(MediaAsset.id != asset.id, MediaAsset.provider == "telegram")):
        other_refs = [decrypt(other.provider_ref_encrypted)]
        other_refs += [decrypt(ref) for ref in (other.segment_refs_encrypted or [])]
        if messages & {(ref.split(":", 2)[0], ref.split(":", 2)[1]) for ref in other_refs}:
            asset.upload_status = "inactive"
            audit(db, None, "media.cleanup_blocked_shared", "media_asset", asset.id)
            db.commit()
            return {"asset": None, "blocked": True}
    asset.upload_status = "cleanup_processing"
    db.commit()
    return {"asset": {"id": asset.id, "refs": list(dict.fromkeys(refs))}}


@router.post("/cleanup/{asset_id}/finish")
def finish_cleanup(asset_id: uuid.UUID, body: CleanupResultIn, db: Session = Depends(get_db)):
    asset = db.scalar(select(MediaAsset).where(MediaAsset.id == asset_id).with_for_update())
    if asset is None or asset.upload_status != "cleanup_processing":
        raise AppError(409, "INVALID_CLEANUP_STATE", "Asset is not being cleaned up.")
    asset.upload_status = "deleted" if body.success else "cleanup_failed"
    audit(db, None, "media.cleanup_succeeded" if body.success else "media.cleanup_failed",
          "media_asset", asset.id, {"error_code": None if body.success else body.error_code})
    db.commit()
    return {"id": asset.id, "status": asset.upload_status, "telegram_deleted": body.success}

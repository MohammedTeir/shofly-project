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
from app.models import Episode, ImportJob, MediaAsset, Movie, User
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



class RefreshSourceIn(BaseModel):
    source_ref: str = Field(min_length=8, max_length=2000)


@router.post("/{jid}/refresh-source")
def refresh_source(jid: uuid.UUID, body: RefreshSourceIn, admin: User = Depends(staff),
                   db: Session = Depends(get_db)):
    """Replace an expired direct URL and requeue the same approved import job."""
    j = db.scalar(select(ImportJob).where(ImportJob.id == jid).with_for_update())
    if j is None:
        raise AppError(404, "NOT_FOUND", "Not found.")
    if j.source_type != "direct_url" or j.status not in ("FAILED", "EXPIRED_SOURCE", "RETRY_WAIT"):
        raise AppError(409, "INVALID_TRANSITION", "Source can only be refreshed for a stopped direct URL import.")
    if j.lease_owner is not None:
        raise AppError(409, "JOB_LEASED", "Wait until the active worker lease has ended.")
    if not j.candidate_kind or not j.target_id or not has_valid_rights(db, j.candidate_kind, j.target_id):
        raise AppError(409, "RIGHTS_NOT_APPROVED", "Approved rights are required before retrying.")
    try:
        validate_source_url(body.source_ref, get_settings().import_hosts)
    except UnsafeURL as exc:
        raise AppError(422, "UNSAFE_SOURCE", f"Source rejected ({exc}).")
    j.source_ref_encrypted = encrypt(body.source_ref)
    j.status = "READY"
    j.lease_epoch += 1
    j.lease_owner = j.lease_until = j.next_attempt_at = None
    j.attempts = 0
    j.progress_percent = 0
    j.error_code = j.error_message_safe = None
    audit(db, admin.id, "import.source_refresh", "import_job", j.id,
          {"source_type": "direct_url", "url_redacted": True})
    db.commit()
    return out(j)


@router.post("/{jid}/cancel")
def cancel(jid: uuid.UUID, admin: User = Depends(staff), db: Session = Depends(get_db)):
    j = _job(db, jid)
    transition(j, "CANCELLED")
    audit(db, admin.id, "import.cancel", "import_job", j.id)
    db.commit()
    return out(j)


@router.get("/assets/{kind}/{target_id}")
def list_media_assets(kind: Literal["movie", "episode"], target_id: uuid.UUID,
                      admin: User = Depends(staff), db: Session = Depends(get_db)):
    """List stored variants without disclosing private Telegram references."""
    model = Movie if kind == "movie" else Episode
    if db.get(model, target_id) is None:
        raise AppError(404, "NOT_FOUND", "Target does not exist.")
    col = MediaAsset.movie_id if kind == "movie" else MediaAsset.episode_id
    assets = db.scalars(select(MediaAsset).where(col == target_id).order_by(MediaAsset.created_at.desc()))
    return {"items": [{"id": a.id, "quality": a.quality, "edition": a.edition,
                       "size_bytes": a.size_bytes, "checksum_sha256": a.checksum_sha256,
                       "upload_status": a.upload_status, "created_at": a.created_at}
                      for a in assets]}


@router.post("/assets/{asset_id}/deactivate")
def deactivate_media_asset(asset_id: uuid.UUID, admin: User = Depends(staff), db: Session = Depends(get_db)):
    """Revoke delivery immediately. Never delete the only copy from Telegram implicitly."""
    a = db.scalar(select(MediaAsset).where(MediaAsset.id == asset_id).with_for_update())
    if a is None:
        raise AppError(404, "NOT_FOUND", "Asset does not exist.")
    if a.upload_status != "inactive":
        a.upload_status = "inactive"
        audit(db, admin.id, "media.deactivate", "media_asset", a.id)
        db.commit()
    return {"id": a.id, "upload_status": a.upload_status, "telegram_deleted": False}


@router.post("/assets/{asset_id}/restore")
def restore_media_asset(asset_id: uuid.UUID, admin: User = Depends(staff), db: Session = Depends(get_db)):
    a = db.scalar(select(MediaAsset).where(MediaAsset.id == asset_id).with_for_update())
    if a is None:
        raise AppError(404, "NOT_FOUND", "Asset does not exist.")
    if a.upload_status != "verified":
        a.upload_status = "verified"
        audit(db, admin.id, "media.restore", "media_asset", a.id)
        db.commit()
    return {"id": a.id, "upload_status": a.upload_status}


class ReplaceAssetIn(BaseModel):
    replacement_asset_id: uuid.UUID


@router.post("/assets/{asset_id}/replace")
def replace_media_asset(asset_id: uuid.UUID, body: ReplaceAssetIn,
                        admin: User = Depends(staff), db: Session = Depends(get_db)):
    """Atomically switch delivery to an already verified replacement for the same title.

    Telegram messages are deliberately retained; physical deletion requires a separate,
    failure-aware storage cleanup workflow. This endpoint is safe to retry.
    """
    if asset_id == body.replacement_asset_id:
        raise AppError(409, "INVALID_REPLACEMENT", "Select a different replacement asset.")
    assets = list(db.scalars(select(MediaAsset).where(
        MediaAsset.id.in_([asset_id, body.replacement_asset_id])).order_by(MediaAsset.id).with_for_update()))
    old = next((a for a in assets if a.id == asset_id), None)
    new = next((a for a in assets if a.id == body.replacement_asset_id), None)
    if old is None or new is None:
        raise AppError(404, "NOT_FOUND", "Asset does not exist.")
    if old.movie_id != new.movie_id or old.episode_id != new.episode_id:
        raise AppError(409, "TARGET_MISMATCH", "Both assets must belong to the same movie or episode.")
    if old.upload_status not in ("verified", "inactive") or new.upload_status != "verified":
        raise AppError(409, "REPLACEMENT_NOT_VERIFIED", "Replacement must be verified and active.")
    kind, target = ("movie", old.movie_id) if old.movie_id else ("episode", old.episode_id)
    if not has_valid_rights(db, kind, target):
        raise AppError(409, "RIGHTS_NOT_APPROVED", "Valid content rights are required.")
    old.upload_status = "inactive"
    audit(db, admin.id, "media.replace", "media_asset", old.id,
          {"replacement_asset_id": str(new.id), "telegram_deleted": False})
    db.commit()
    return {"old_asset_id": old.id, "replacement_asset_id": new.id,
            "old_status": "inactive", "replacement_status": "verified", "telegram_deleted": False}


@router.post("/assets/{asset_id}/request-cleanup")
def request_media_cleanup(asset_id: uuid.UUID, admin: User = Depends(staff), db: Session = Depends(get_db)):
    """Mark an inactive Telegram asset for operator-controlled storage cleanup.

    This does NOT claim that Telegram deleted anything. A separate authenticated
    cleanup worker must confirm remote deletion before the record is purged.
    """
    asset = db.scalar(select(MediaAsset).where(MediaAsset.id == asset_id).with_for_update())
    if asset is None:
        raise AppError(404, "NOT_FOUND", "Asset does not exist.")
    if asset.provider != "telegram":
        raise AppError(409, "UNSUPPORTED_PROVIDER", "Only Telegram assets support storage cleanup.")
    if asset.upload_status not in ("inactive", "cleanup_pending"):
        raise AppError(409, "ASSET_STILL_ACTIVE", "Disable the asset before requesting cleanup.")
    if asset.upload_status == "cleanup_pending":
        return {"id": asset.id, "status": "cleanup_pending", "telegram_deleted": False}
    # A shared Telegram message must never be removed while referenced by another asset.
    # Compare encrypted references by decrypting in memory (Fernet is randomized).
    refs = {decrypt(asset.provider_ref_encrypted)}
    refs.update(decrypt(ref) for ref in (asset.segment_refs_encrypted or []))
    others = db.scalars(select(MediaAsset).where(MediaAsset.id != asset.id, MediaAsset.provider == "telegram"))
    for other in others:
        other_refs = {decrypt(other.provider_ref_encrypted)}
        other_refs.update(decrypt(ref) for ref in (other.segment_refs_encrypted or []))
        if refs & other_refs:
            raise AppError(409, "SHARED_STORAGE_REFERENCE", "Storage messages are referenced by another asset.")
    asset.upload_status = "cleanup_pending"
    audit(db, admin.id, "media.cleanup_requested", "media_asset", asset.id,
          {"telegram_deleted": False})
    db.commit()
    return {"id": asset.id, "status": "cleanup_pending", "telegram_deleted": False}

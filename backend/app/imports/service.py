import uuid
from datetime import datetime, timedelta, timezone
from sqlalchemy import and_, or_, select, update
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.core.crypto import decrypt
from app.core.errors import AppError
from app.imports.state import WORKER, transition
from app.models import ImportJob


def utcnow(): return datetime.now(timezone.utc)


def as_utc(d: datetime | None):
    return d if d is None or d.tzinfo else d.replace(tzinfo=timezone.utc)


def claim_next(db: Session, owner: str) -> ImportJob | None:
    """Atomic claim: pick a candidate (SKIP LOCKED on Postgres) then compare-and-set on lease_epoch,
    so two workers can never both own a job. Also reclaims jobs whose lease expired."""
    s, now = get_settings(), utcnow()
    for _ in range(5):
        cand = db.scalar(select(ImportJob).where(or_(
            ImportJob.status == "READY",
            and_(ImportJob.status == "RETRY_WAIT", ImportJob.next_attempt_at <= now),
            and_(ImportJob.status.in_(WORKER), ImportJob.lease_until < now),
        )).order_by(ImportJob.created_at).limit(1).with_for_update(skip_locked=True))
        if cand is None:
            return None
        if cand.attempts >= s.job_max_attempts:  # lease kept expiring: stop retrying
            cand.status, cand.lease_owner, cand.lease_until = "FAILED", None, None
            cand.error_code, cand.error_message_safe = "MAX_ATTEMPTS", "Worker lease expired too many times."
            db.commit()
            continue
        res = db.execute(update(ImportJob).where(
            ImportJob.id == cand.id, ImportJob.status == cand.status, ImportJob.lease_epoch == cand.lease_epoch
        ).values(status="DOWNLOADING", lease_owner=owner, lease_until=now + timedelta(seconds=s.job_lease_seconds),
                 attempts=cand.attempts + 1, lease_epoch=cand.lease_epoch + 1, progress_percent=0,
                 error_code=None, error_message_safe=None, updated_at=now))
        db.commit()
        if res.rowcount == 1:
            db.expire_all()
            return db.get(ImportJob, cand.id)
    return None


def owned_job(db: Session, job_id: uuid.UUID, owner: str) -> ImportJob:
    job = db.get(ImportJob, job_id)
    if job is None:
        raise AppError(404, "NOT_FOUND", "Not found.")
    if job.status == "CANCELLED":
        raise AppError(409, "JOB_CANCELLED", "Job was cancelled.")
    if job.lease_owner != owner:
        raise AppError(409, "LEASE_LOST", "This worker no longer owns the job.")
    if as_utc(job.lease_until) < utcnow():
        raise AppError(409, "LEASE_EXPIRED", "Lease expired.")
    if job.status not in WORKER:
        raise AppError(409, "INVALID_STATE", "Job is not being processed.")
    return job


def claim_payload(job: ImportJob) -> dict:
    s = get_settings()
    return {"id": job.id, "source_type": job.source_type, "source_ref": decrypt(job.source_ref_encrypted),
            "candidate_kind": job.candidate_kind, "target_id": job.target_id, "attempts": job.attempts,
            "max_attempts": s.job_max_attempts, "lease_seconds": s.job_lease_seconds}


def to_retry_or_fail(job: ImportJob, code: str, msg: str | None, retryable: bool) -> None:
    s = get_settings()
    job.error_code, job.error_message_safe = code, (msg or "")[:300] or None
    if code == "SOURCE_EXPIRED":
        transition(job, "EXPIRED_SOURCE")
    elif retryable and job.attempts < s.job_max_attempts:
        transition(job, "RETRY_WAIT")
        job.next_attempt_at = utcnow() + timedelta(seconds=s.retry_backoff_seconds * 2 ** (job.attempts - 1))
    else:
        transition(job, "FAILED")

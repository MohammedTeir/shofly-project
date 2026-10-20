from app.core.errors import AppError

WORKER = {"DOWNLOADING", "PROBING", "PROCESSING", "UPLOADING", "VERIFYING"}
_FAIL = {"RETRY_WAIT", "FAILED", "EXPIRED_SOURCE", "CANCELLED", "BLOCKED_RIGHTS"}
TRANSITIONS: dict[str, set[str]] = {
    "PENDING": {"ANALYZING", "NEEDS_REVIEW", "CANCELLED", "FAILED"},
    "ANALYZING": {"MATCHING", "NEEDS_REVIEW", "FAILED", "CANCELLED"},
    "MATCHING": {"NEEDS_REVIEW", "READY", "FAILED", "CANCELLED"},
    "NEEDS_REVIEW": {"READY", "CANCELLED"},
    "READY": {"DOWNLOADING", "CANCELLED", "BLOCKED_RIGHTS"},
    "DOWNLOADING": {"PROBING"} | _FAIL,
    "PROBING": {"PROCESSING", "UPLOADING"} | _FAIL,
    "PROCESSING": {"UPLOADING"} | _FAIL,
    "UPLOADING": {"VERIFYING"} | _FAIL,
    "VERIFYING": {"COMPLETED"} | _FAIL,
    "RETRY_WAIT": {"DOWNLOADING", "CANCELLED", "FAILED"},
    "BLOCKED_RIGHTS": {"NEEDS_REVIEW", "CANCELLED"},
    "EXPIRED_SOURCE": {"NEEDS_REVIEW", "CANCELLED"},
    "FAILED": {"READY"},  # explicit admin retry only
    "COMPLETED": set(), "CANCELLED": set(),
}


def transition(job, new: str) -> None:
    if new not in TRANSITIONS.get(job.status, set()):
        raise AppError(409, "INVALID_TRANSITION", f"Cannot move job from {job.status} to {new}.")
    job.status = new
    if new not in WORKER:  # leaving worker ownership
        job.lease_owner = job.lease_until = None

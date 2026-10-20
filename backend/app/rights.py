import uuid
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import ContentRight


def has_valid_rights(db: Session, kind: str, content_id: uuid.UUID, at: datetime | None = None) -> bool:
    """Approved, in-window record that permits at least one delivery platform. Checked at use time, never cached."""
    at = at or datetime.now(timezone.utc)
    return db.scalar(select(ContentRight.id).where(
        ContentRight.content_kind == kind, ContentRight.content_id == content_id,
        ContentRight.review_status == "APPROVED", ContentRight.valid_from <= at, ContentRight.valid_until >= at,
        (ContentRight.telegram_allowed.is_(True)) | (ContentRight.web_allowed.is_(True))).limit(1)) is not None

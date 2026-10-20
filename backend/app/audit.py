import uuid
from sqlalchemy.orm import Session
from app.models import AuditLog


def audit(db: Session, actor_id: uuid.UUID | None, action: str, kind: str, entity_id: uuid.UUID | None, meta: dict | None = None):
    """Append-only; added to the caller's transaction so change + audit commit together."""
    db.add(AuditLog(actor_id=actor_id, action=action, entity_kind=kind, entity_id=entity_id, metadata_redacted=meta or {}))

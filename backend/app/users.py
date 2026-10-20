from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.models import User


def normalize_lang(code: str | None) -> str | None:
    if not code:
        return None
    base = code.lower().replace("_", "-").split("-")[0]
    return base if base in get_settings().languages else None


def get_or_create_user(db: Session, tg: dict) -> User:
    """One account per telegram_id. Language is only seeded on creation (I18N-02/10)."""
    tid = int(tg["id"])
    user = db.scalar(select(User).where(User.telegram_id == tid))
    if user is None:
        s = get_settings()
        suggested = normalize_lang(tg.get("language_code"))
        user = User(
            telegram_id=tid, username=tg.get("username"),
            display_name=" ".join(x for x in (tg.get("first_name"), tg.get("last_name")) if x) or None,
            preferred_language=suggested or s.default_language,
            language_source="telegram" if suggested else "default",
            language_updated_at=datetime.now(timezone.utc),
        )
        db.add(user)
        try:
            db.commit()
        except IntegrityError:  # concurrent first login
            db.rollback()
            user = db.scalar(select(User).where(User.telegram_id == tid))
    return user


def set_language(db: Session, user: User, lang: str) -> User:
    user.preferred_language = lang
    user.language_source = "user"
    user.language_updated_at = datetime.now(timezone.utc)
    db.commit()
    return user

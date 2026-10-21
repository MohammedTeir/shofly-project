from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.audit import audit
from app.models import User

ROLES = {"member", "moderator", "content_admin", "rights_admin", "super_admin"}


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


def set_role(db: Session, telegram_id: int, role: str) -> User:
    """Operator-level role grant (bootstrap). Creates the row if the person never opened the bot; they keep it on first login."""
    if role not in ROLES:
        raise ValueError(f"role must be one of {sorted(ROLES)}")
    u = db.scalar(select(User).where(User.telegram_id == telegram_id))
    if u is None:
        u = User(telegram_id=telegram_id, preferred_language=get_settings().default_language, language_source="default")
        db.add(u); db.flush()
    u.role = role
    audit(db, None, "user.bootstrap_role", "user", u.id, {"role": role})
    db.commit()
    return u


def bootstrap_admins(db: Session) -> list[int]:
    """Promote the Telegram ids listed in BOOTSTRAP_SUPER_ADMIN_TELEGRAM_IDS (env, set by the operator). Idempotent:
    already-super admins are untouched. Note: while an id stays in the variable it is re-promoted at every start."""
    done = []
    for tid in get_settings().bootstrap_admin_ids:
        u = db.scalar(select(User).where(User.telegram_id == tid))
        if u is None or u.role != "super_admin":
            set_role(db, tid, "super_admin"); done.append(tid)
    return done

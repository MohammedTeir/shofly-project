"""Bootstrap the first admin (nobody can grant roles until a super_admin exists).
Usage: python -m scripts.make_admin --telegram-id 123456789 --role super_admin"""
import argparse
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.routes_admin_catalog import ROLES
from app.audit import audit
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.models import User


def set_role(db: Session, telegram_id: int, role: str) -> User:
    if role not in ROLES:
        raise ValueError(f"role must be one of {sorted(ROLES)}")
    u = db.scalar(select(User).where(User.telegram_id == telegram_id))
    if u is None:  # allowed before the person ever opened the bot; they keep this row on first login
        u = User(telegram_id=telegram_id, preferred_language=get_settings().default_language, language_source="default")
        db.add(u); db.flush()
    u.role = role
    audit(db, None, "user.bootstrap_role", "user", u.id, {"role": role})
    db.commit()
    return u


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--telegram-id", type=int, required=True)
    ap.add_argument("--role", default="super_admin")
    a = ap.parse_args()
    with SessionLocal() as s:
        u = set_role(s, a.telegram_id, a.role)
    print(f"telegram_id={a.telegram_id} is now {u.role}")

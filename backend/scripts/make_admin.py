"""Bootstrap the first admin (nobody can grant roles until a super_admin exists).
Usage: python -m scripts.make_admin --telegram-id 123456789 --role super_admin
No shell on your host (e.g. Render free)? Set BOOTSTRAP_SUPER_ADMIN_TELEGRAM_IDS instead."""
import argparse
from app.core.db import SessionLocal
from app.users import set_role  # noqa: F401  (re-exported for tests/scripts)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--telegram-id", type=int, required=True)
    ap.add_argument("--role", default="super_admin")
    a = ap.parse_args()
    with SessionLocal() as s:
        u = set_role(s, a.telegram_id, a.role)
    print(f"telegram_id={a.telegram_id} is now {u.role}")

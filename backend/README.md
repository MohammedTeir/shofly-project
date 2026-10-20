# TML backend — Milestones 1–2

Run: `pip install -r requirements.txt && cp .env.example .env`
Migrate (Postgres): `alembic upgrade head` · Dev seed (fictional titles): `python -m scripts.seed`
Serve: `uvicorn app.main:app --reload` · Test: `python -m pytest -q`

Implemented: Telegram initData auth (HMAC + freshness), JWT, one account per telegram_id, persistent language
(server beats Telegram locale), localized catalog with fallback, search, keyset-free offset pagination,
movie/series/season/collection endpoints, idempotent per-user favorites, admin draft creation,
translations upsert, audit log (written in the same transaction), RBAC, auth rate limit, Alembic 0001.

Deliberately not here: publish endpoint (needs rights + verified asset, Milestones 4/6), watch progress
(needs media_assets), Postgres CI run, distributed rate limiting, Arabic-aware search (plain ILIKE for now).

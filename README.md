# Shofly | شوفلي — Telegram media library

backend/ FastAPI + PostgreSQL (SQLite for dev) · apps/telegram-bot (aiogram) · apps/mini-app (Shofly) ·
apps/admin-dashboard (Shofly Admin) · workers/media-worker + notebooks/media_worker.ipynb (Colab) · specification: TML-MPS-001 v2.1

## Flow
1. Admin creates a title, adds a rights record (rights admin approves), submits an authorized import link and approves it for the title.
2. The Colab worker downloads, probes, uploads to the private Telegram channel, verifies, reports completion.
3. Admin marks metadata verified and publishes (blocked unless: metadata verified + verified file + approved, in-date rights).
4. Members see the title. "Send via Telegram" (Mini App) or the bot button re-checks rights/platform/territory/entitlement
   on every request, then the bot copies the file into the user's chat with forwarding disabled.
Takedown: unpublish, revoke rights, or let the license expire: delivery stops on the next request.

## Local run
backend: `cp .env.example .env` (fill secrets) · `alembic upgrade head` · `python -m scripts.seed` (DEV fixtures) · `uvicorn app.main:app`
bot: `python -m tgbot.main` · apps: `npm install && npm run dev` · worker: see workers/media-worker/README.md
Tests: `python -m pytest -q` in backend, apps/telegram-bot, workers/media-worker; `npm test` in both web apps.

## Not built yet (see spec)
Gemini/TMDB matching (M3), content requests (REQ), subscriptions/Stars (M7), web playback/object storage, watch progress,
Telegram webhook mode, deployment/CI/monitoring (M8), live-Telegram verification of the bot and Telegram storage provider.

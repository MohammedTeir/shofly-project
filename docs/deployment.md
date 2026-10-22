# Deployment guide (Shofly)

## 0. Reality check
Docker/compose files and the CI workflow here are **untested on real infrastructure** (no Docker or GitHub in the build sandbox).
Verified: backend + bot + worker tests on SQLite **and PostgreSQL 16**, migrations up/down/up with no model drift, a real
`uvicorn` boot on Postgres passing `scripts/smoke`. Never verified: a live Telegram bot, the Telegram storage channel, Colab.
Free tiers sleep: the **API and the bot must run on an always-on host** (small VPS or a platform's paid/always-on tier).

## 1. One-time Telegram setup
1. @BotFather: `/newbot` → note the token and username. Keep the token secret; if it was ever pasted anywhere public, `/revoke` it.
2. Create a **private channel** for file storage; add the bot as an **administrator** (post + delete messages). Note the channel id (`-100…`).
3. Host the two static apps (`npm run build` → upload `dist/`) over HTTPS (Cloudflare Pages, Netlify, GitHub Pages…).
4. @BotFather → `/mybots` → Bot Settings → Menu Button → set the Mini App URL (Shofly). For Shofly Admin use a second bot or a
   separate Mini App (`/newapp`) so only admins are shown the link; the backend enforces roles regardless.

## 2. Configure and start
```bash
cp .env.example .env        # fill every <placeholder>; generate secrets as the file explains
docker compose up -d --build
docker compose logs -f backend      # migrations run on start
python -m scripts.smoke https://<your-api-host>     # run from backend/; expect 8 x PASS
docker compose exec backend python -m scripts.make_admin --telegram-id <YOUR_TELEGRAM_ID> --role super_admin
```
Put a TLS reverse proxy in front of port 8000 (Caddy/nginx or your platform); Mini Apps require HTTPS. Add your static app origins
to `CORS_ORIGINS`. Find your Telegram id by messaging @userinfobot.

Supabase instead of the bundled Postgres: set `DATABASE_URL=postgresql+psycopg://…` to the **direct or session-mode** connection
(not transaction pooler) and drop the `db` service. Verify its free-tier limits yourself.

## 3. First content (end to end)
1. Admin app → Titles → create a title. Rights → create a record (evidence reference, platform, territory, dates) → a **rights admin**
   approves. Imports → submit an authorized HTTPS link (host must be in `IMPORT_ALLOWED_HOSTS`) → approve for the title.
2. Colab: upload `workers/media-worker`, open `notebooks/media_worker.ipynb`, add Colab Secrets
   (`SHOFLY_API_URL`, `WORKER_API_TOKEN`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_STORAGE_CHANNEL_ID`), run all cells. Telegram's hosted
   Bot API allows ≤ 50 MB uploads; larger files need a self-hosted Bot API server or another provider (not built).
3. Admin app → title → Mark metadata verified → Publish. Open the bot → the title appears → "Send me the file".
Use only media you own or are licensed to distribute.

## 4. Updating
`git pull && docker compose up -d --build`. Migrations apply on start; for several replicas run `alembic upgrade head` once as a job.
API change? CI fails until `python -m scripts.export_openapi` is re-run and the snapshot committed (review the diff first).

## 5. Known gaps before a public launch
Telegram webhook mode (bot uses long polling, one instance only), DNS-rebinding hardening of imports, distributed rate limiting
(in-process, per instance), automated backups, alerting, load testing, Gemini/TMDB matching, requests, subscriptions, privacy
notice and data-deletion workflow (spec 13.3), legal review of your content rights.


## Current Colab deployment notes (October 2026)

The earlier first-content instructions about the hosted Bot API 50 MB limit are outdated for the current large-file worker. Open `https://colab.research.google.com/github/MohammedTeir/shofly-project/blob/main/notebooks/media_worker.ipynb`, use Python 3 / CPU, and run all cells. Telethon MTProto uploads large files to the private Telegram channel; the notebook sets four parallel upload workers. Ensure the bot/session has permission to post and delete messages in that channel. Review the worker README for diagnostics and cleanup limitations.

GitHub commits do not guarantee Vercel deployment. When Vercel reports `api-deployments-free-per-day`, wait for its quota to reset and avoid repeated redeploy attempts. Verify that the admin dashboard and backend have deployed the same compatible version before using new API actions. Do not use movie-level permanent deletion in production until its end-to-end flow has been validated.

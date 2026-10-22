# Shofly | شوفلي

**Telegram-first movie and TV library** with an admin dashboard, Telegram Mini App, FastAPI backend, PostgreSQL, and an on-demand Google Colab media worker.

> **Project status (October 2026):** Active development. The repository includes working import, rights, catalog, Telegram storage, cleanup, and parallel-transfer implementations. Production end-to-end reliability, performance and latest CI status must be verified independently. Only import or distribute media for which you have the necessary rights.

## Applications and deployment

| Component | Technology | Deployment |
| --- | --- | --- |
| Backend/API | FastAPI, SQLAlchemy, Alembic | [Render](https://shofly-backend.onrender.com) |
| Database | PostgreSQL | Neon (connection secret on Render) |
| Telegram bot | aiogram | [@shofly_bot](https://t.me/shofly_bot), Render |
| Mini App | Vite frontend | [shofly-mini.vercel.app](https://shofly-mini.vercel.app) |
| Admin Dashboard | Vite frontend | [shofly-admin.vercel.app](https://shofly-admin.vercel.app) |
| Media worker | Python, HTTPX, ffprobe/ffmpeg, Telethon | Google Colab or local Python |
| File storage | Private Telegram channel | MTProto upload by worker |

Backend health: [live](https://shofly-backend.onrender.com/health/live) · [ready](https://shofly-backend.onrender.com/health/ready). These links are endpoints, **not** a claim that the services are healthy at the moment you read this document. Render free instances may sleep.

## Architecture

```text
Telegram users ──► @shofly_bot ──────┐
       └────────► Telegram Mini App ─┤
Admin ──────────► Admin Dashboard ───┤
                                     ▼
                               FastAPI Backend ◄────► Neon PostgreSQL
                                     ▲
                              WORKER_API_TOKEN
                                     │
                           Colab / local media worker
                                     │
                    HTTPS source ──► HTTPX downloader
                                     │
                          ffprobe / optional ffmpeg
                                     │
                        Telethon MTProto uploader
                                     │
                           Private Telegram channel
```

**Import flow:** Create title → register and approve rights → create import job with an authorized HTTPS source → approve import → worker claims job → download → probe/verify → upload to Telegram → verify and report → verify metadata → publish. Access/delivery is subject to rights, availability, and applicable entitlement checks.

**Deletion flow:** Admin requests **Delete movie & Telegram files** → movie enters deletion state → worker deletes registered Telegram messages and reports confirmation → backend finalizes related movie records and import jobs. This is destructive and should be used only after backup and end-to-end validation. Lost or overwritten Telegram message references cannot be automatically discovered.

## Repository layout

```text
backend/                         FastAPI API, database models/migrations, tests
apps/telegram-bot/               Telegram bot
apps/mini-app/                   Member-facing Telegram Mini App
apps/admin-dashboard/            Admin console
workers/media-worker/            Downloader, probes, uploaders, cleanup, tests
notebooks/media_worker.ipynb      Colab setup and execution
services/stream-gateway/         Separate gateway component
```

## Backend configuration (Render)

Deploy the `backend/` Docker context and configure required secrets in the Render service (do **not** commit them).

```dotenv
APP_ENV=production
DATABASE_URL=postgresql+psycopg://...
TELEGRAM_BOT_TOKEN=<BotFather token>
JWT_SIGNING_KEY=<random secret>
BOT_API_TOKEN=<bot-to-backend token>
WORKER_API_TOKEN=<worker-to-backend token>
ENCRYPTION_KEY=<Fernet key>
BOT_USERNAME=shofly_bot
CORS_ORIGINS=https://shofly-mini.vercel.app,https://shofly-admin.vercel.app
BOOTSTRAP_SUPER_ADMIN_TELEGRAM_IDS=<your numeric Telegram ID>
IMPORT_ALLOWED_HOSTS=
```

`IMPORT_ALLOWED_HOSTS` is an **optional, comma-separated hostname allowlist**. Empty means no additional hostname restriction; it **does not disable** URL validation. Sources must be HTTPS, resolve to public IP addresses and use an accepted port. As of October 22, 2026, the code also permits HTTPS port `8443` for the **exact** hostname `d900.userdrive.org`; other custom ports remain blocked. The worker applies corresponding checks, including redirect validation. Do not treat URL validation as a guarantee against every DNS-rebinding or network-level attack.

The backend and worker must use the **same** `WORKER_API_TOKEN`. Keep `BOT_API_TOKEN` separate from the Telegram BotFather token.

## Telegram bot (Render)

```dotenv
API_BASE_URL=https://shofly-backend.onrender.com
TELEGRAM_BOT_TOKEN=<BotFather token>
BOT_API_TOKEN=<matching backend token>
PUBLIC_APP_URL=https://shofly-mini.vercel.app
```

Bot command: `cd apps/telegram-bot && python -m tgbot.main`. The current bot uses long polling; the Render web-service process exposes a lightweight HTTP health listener when `PORT` is supplied. Do not run two polling instances of the same bot simultaneously.

## Frontends (Vercel)

Set `VITE_API_BASE_URL=https://shofly-backend.onrender.com` in both Vercel projects. Their respective root directories are `apps/mini-app` and `apps/admin-dashboard`; build with `npm run build`, output `dist`. Open admin authentication through its intended Telegram entry point.

## Colab worker — recommended media workflow

Use [`notebooks/media_worker.ipynb`](notebooks/media_worker.ipynb). Keep tokens in Colab Secrets, never in notebook source or GitHub. The notebook reads:

- `SHOFLY_API_URL`, `WORKER_API_TOKEN`
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_STORAGE_CHANNEL_ID`
- `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`

The bot must have appropriate access to the private storage channel. The notebook sets up the Python worker, ffmpeg tools, API connectivity and Telethon storage provider.

**After a GitHub worker update:** rerun the notebook's repository update/install cell (**cell 3** in the current workflow), configuration (**cell 5**), initialization/provider (**cell 7**) and processing (**cell 11**). If modules were already imported in the runtime, **restart the Colab runtime and rerun the setup** to ensure new Python code is loaded. Notebook cell positions can change; follow cell content if numbering differs.

### Parallel HTTPX downloads

The default downloader is `httpx`, not aria2c. It now supports **concurrent HTTP byte-range requests**. The current Colab notebook configures:

```python
USE_ARIA2 = False
os.environ["DOWNLOADER"] = "httpx"
os.environ["HTTPX_PARALLEL_CONNECTIONS"] = "8"
os.environ["HTTPX_CHUNK_SIZE_MB"] = "8"
```

**Behavior:**

1. Probe the source using a one-byte `Range` request, validating redirects.
2. If the source returns a valid `206 Partial Content` with a known total size, divide it into bounded chunks.
3. Download up to eight chunks concurrently, validate each `Content-Range`, and write each chunk at its correct offset.
4. Verify completed file size and compute SHA-256 before proceeding.
5. If byte ranges are unsupported at the initial probe, fall back to the existing single-stream HTTPX downloader.

Settings: `HTTPX_PARALLEL_CONNECTIONS` (1–32, default 8) and `HTTPX_CHUNK_SIZE_MB` (default 8; at least 1). Parallelism can improve throughput **only when the source supports ranges and has available bandwidth**. Test 1, 4, 8 and 16 connections against the same authorized source; more connections are not necessarily faster. The new parallel implementation has automated tests but **has not yet been verified with a real UserDrive download in Colab**.

The alternate `aria2c` downloader remains in the repository. It is opt-in and requires a source hostname allowlist; the default Colab path does **not** require enabling it or adding `TRUSTED_SOURCE_HOSTS`.

### Parallel Telegram MTProto uploads

The Colab notebook currently sets:

```python
os.environ["MTPROTO_CONNECTIONS"] = "4"
os.environ["MTPROTO_PARALLEL_WORKERS"] = "16"
```

The worker uses Telethon MTProto to send 512 KiB file parts with up to **four independent MTProto clients and sixteen concurrent upload tasks**. It verifies the uploaded Telegram asset before reporting successful completion. Configurable defaults are in `workers/media-worker/shofly_worker/config.py`. These settings are distinct from the **50 MB hosted Bot API** upload limit; Telegram's own applicable MTProto limits still apply. Large files may be split into playable segments according to worker settings.

Inspect `upload_parallel_summary`, `segment_verified`, `job_completed` and the final processed outcomes. An earlier **four-worker, single-connection** experiment transferred approximately 1,202 MiB in 385 seconds (~3.12 MiB/s). This is historical baseline data, **not** a benchmark of the newer four-connection/sixteen-worker configuration.

### Other worker settings

```dotenv
API_BASE_URL=https://shofly-backend.onrender.com
WORKER_API_TOKEN=<matching backend secret>
DOWNLOADER=httpx
HTTPX_PARALLEL_CONNECTIONS=8
HTTPX_CHUNK_SIZE_MB=8
DOWNLOAD_MAX_BYTES=8589934592
DOWNLOAD_TIMEOUT=1800
MTPROTO_CONNECTIONS=4
MTPROTO_PARALLEL_WORKERS=16
SPLIT_LARGE_MEDIA=true
SEGMENT_MAX_BYTES=1992294400
FFMPEG_VERIFY=true
FFMPEG_VERIFY_TIMEOUT=600
```

These are representative settings; notebook configuration takes precedence when it sets the environment. Worker `ALLOWED_HOSTS` is an optional additional hostname restriction. Downloaded media uses temporary local storage unless an optional persistent-download configuration is enabled for aria2c.

Run locally:

```bash
cd workers/media-worker
pip install -r requirements.txt
python -m shofly_worker
```

Install `ffmpeg`/`ffprobe` on the host. The CLI polls for jobs; a notebook can instead call `run_until_empty` to process queued work and pending cleanup.

## Admin operations

1. **Titles:** create a movie or series and enter metadata.
2. **Rights:** create the appropriate rights record with valid dates, territories and Telegram permission; have it approved by an authorized role.
3. **Imports:** submit a direct HTTPS source and associate it with the correct target title; approve the import.
4. **Worker:** run Colab to process the job; confirm download, media probing, upload and verification.
5. **Publishing:** verify metadata and publish only after prerequisites are satisfied.
6. **Cleanup:** use the explicit delete action to queue registered Telegram assets for deletion; run the worker again to finish cleanup.

Only use media you own or are licensed to distribute. A reachable source URL does not itself grant redistribution rights.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Render backend takes time to respond | Free instance may be asleep; check `/health/live` and `/health/ready` |
| Bot is silent | Render logs, polling process, token, duplicate polling instances |
| Admin says “Open from Telegram” | Open via Telegram's intended authentication flow |
| Admin access denied | Bootstrap admin ID, assigned role and deployment |
| Frontend network/CORS error | `VITE_API_BASE_URL`, `CORS_ORIGINS`, backend availability |
| “Source rejected: host not allowed or address unsafe” | HTTPS, hostname allowlist, public DNS/IP, accepted port, backend deployment |
| UserDrive `:8443` rejected | Exact `d900.userdrive.org` hostname, updated Render backend, correct URL |
| Job remains READY | Colab worker not running, wrong `WORKER_API_TOKEN`, unapproved import/rights |
| `UNSAFE_SOURCE` | Worker URL or redirect failed validation; inspect hostname/port/redirects |
| `INVALID_RANGE` | Source ignored or returned inconsistent byte-range data; retry with one HTTPX connection |
| `DOWNLOAD_NETWORK_ERROR` / `DOWNLOAD_HTTP_ERROR` | Source connectivity, HTTP response, expiration, rate limits |
| `PROBE_FAILED` / `PROBE_UNAVAILABLE` | Source is not a usable media file, or ffprobe missing |
| `ARIA2_DOWNLOAD_FAILED` | Applies only when aria2c mode is enabled; HTTPX mode does not invoke aria2c |
| `FILE_TOO_LARGE` | Check source download ceiling, MTProto file limit and segment settings |
| `BLOCKED_RIGHTS` | Rights approval, dates, territories and Telegram permission |
| Upload is slow | Compare `upload_parallel_summary` and network throughput; 16 workers is not a speed guarantee |
| Delete action remains pending | Run Colab cleanup worker; inspect registered Telegram references and cleanup logs |

## Local development and tests

```bash
# Backend
cd backend
cp .env.example .env
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload

# Telegram bot
cd ../apps/telegram-bot
pip install -r requirements.txt
python -m tgbot.main

# Frontends (each app directory)
npm install
npm run dev
```

Test suites:

```bash
cd backend && python -m pytest -q
cd ../apps/telegram-bot && python -m pytest -q
cd ../../workers/media-worker && python -m pytest -q
cd ../../apps/mini-app && npm test
cd ../admin-dashboard && npm test
```

CI also validates relevant builds and migration/API contracts. A committed test is not evidence that the latest CI run has passed; check [GitHub Actions](https://github.com/MohammedTeir/shofly-project/actions) for current results.

## Security, secrets and operational limitations

- Never commit Telegram tokens, API tokens, database URLs, Telethon sessions or Colab secrets.
- Generate separate high-entropy secrets for bot-to-backend and worker-to-backend authentication.
- Back up Neon data and validate recovery before destructive movie cleanup.
- Keep source checks and rights enforcement enabled. SSRF validation has known DNS-rebinding limitations and is not a replacement for network egress controls.
- Render free services may sleep; the polling bot may require an always-on service or a future webhook implementation.
- Google Colab is **not** an always-on production worker; runtime lifetime and resource limits apply.
- Parallel HTTPX downloads and the newest MTProto multi-connection uploads require real-world end-to-end validation.
- Telegram storage cleanup covers registered references, not orphaned historical messages.
- A private Telegram channel is not a substitute for rights clearance or durable independent backups.

## Planned / not guaranteed

Subscription billing, Telegram Stars, automated metadata matching, recommendation AI, production monitoring, notifications, webhook bot operation, resumable HTTPX downloads, and browser streaming should be treated as separate features or future work unless verified in their respective code paths.

## Documentation

- [Backend](backend/README.md)
- [Telegram bot](apps/telegram-bot/README.md)
- [Mini App](apps/mini-app/README.md)
- [Admin Dashboard](apps/admin-dashboard/README.md)
- [Media worker](workers/media-worker/README.md)
- [Colab notebook](notebooks/media_worker.ipynb)

---

**Last major documentation refresh:** October 22, 2026. The GitHub repository and code are the source of truth for configuration defaults; deployment state may differ until Render/Vercel redeploy and Colab reload.


## Multi-quality Telegram delivery (October 22, 2026)

**Implemented in code; end-to-end Colab/Telegram validation is still pending.** New imports can generate lower-resolution MP4 versions with FFmpeg and store each version as its own verified Telegram media asset. The Colab notebook sets `GENERATE_QUALITIES=true` and `TRANSCODE_TIMEOUT=7200` seconds; the worker configuration defaults to `GENERATE_QUALITIES=false` outside that notebook to avoid unexpected CPU/storage costs.

- The uploaded original is preserved, including its true probed height (for example `800p`); no upscaling is performed.
- FFmpeg generates eligible lower rungs from `1080p`, `720p`, `480p`, `360p`. For a 1080p original, the generated variants are 720p/480p/360p, while 1080p remains the original. For an 800p original, only 720p/480p/360p are generated.
- Each generated version is uploaded and verified independently, registered under the same movie/episode, and displays its **actual size** in the Telegram quality picker.
- The bot shows a tidy quality-selection screen for movies and episodes. Selecting a quality copies only that version from the private Telegram channel into the user's chat; delivery authorization is rechecked on every request.
- Existing movie deletion queues **all registered quality assets** for Telegram cleanup before finalizing movie removal. This does not recover orphaned messages with missing references.
- Transcoding happens **after the original import is committed**. If generation/upload fails, the original remains available; logs include `quality_generation_incomplete`. Successful versions log `quality_ready`. A newly uploaded but unregistered variant is best-effort cleaned up.
- **Existing movies are not automatically backfilled**. The feature applies to new imports with quality generation enabled; previously uploaded titles need a separate controlled backfill workflow.
- FFmpeg re-encoding is CPU-intensive and can take significant time and disk space on Colab. Quality ladder bitrates are targets, not promises of exact output sizes or perceptual quality. Upload and storage usage multiply with each version.

Check [GitHub Actions](https://github.com/MohammedTeir/shofly-project/actions) and perform a small, licensed test upload before enabling this workflow for valuable media.

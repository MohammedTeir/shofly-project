# Shofly media worker

Run: `python -m shofly_worker` (env: API_BASE_URL, WORKER_API_TOKEN, PROVIDER, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, POLL_SECONDS).

Claims READY import jobs from the backend, downloads from authorized HTTPS sources, runs ffprobe, uploads to a provider,
verifies, then reports completion. Use `notebooks/media_worker.ipynb` in Colab, or run locally:
`pip install -r requirements.txt` then a small script using `shofly_worker.runner.run_until_empty`. Tests: `python -m pytest -q`
(runs the real backend in-process; storage and sources are fakes).

Env: API_BASE_URL, WORKER_API_TOKEN, PROVIDER (local|telegram), TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, MAX_BYTES, TMP_DIR.

Guarantees tested: exclusive claims, lease expiry/reclaim, stale/cancelled workers rejected, completion only after verification,
rights re-checked at completion (media removed from storage if blocked), duplicate checksums never create a second asset,
temp files always removed, error messages never contain URLs or tokens.
Known limits: only `direct_url` sources; no resumable download/upload; no transcoding; DNS rebinding between check and connect;
Telegram provider is unit-tested against a mock API only (hosted Bot API caps uploads at 50 MB, bot delivery only, no browser streaming).

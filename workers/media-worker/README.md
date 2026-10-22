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


## MTProto upload (October 2026)

Use the GitHub-backed `notebooks/media_worker.ipynb` in Google Colab with Python 3, CPU and the latest runtime. Restart/run all cells to fetch updated worker code. The notebook sets `MTPROTO_PARALLEL_WORKERS=4`; the worker configuration also defaults to four. The provider uploads 512 KiB parts through Telethon using a shared client, then sends the assembled video as an MP4 where media probing supports that extension. Four concurrent requests do not mean four independent Telegram connections. GPU acceleration does not speed this transfer.

Logs: `download_finished`, `upload_progress`, `upload_parallel_metrics` (30-second windows), `upload_parallel_summary` (worker count, parts, throughput, request latency and retries), `segment_verified`, `job_completed`. Check `processed: ... {'COMPLETED': ...}` to confirm successful jobs. Real upload example: 1,202.1 MiB, 2,405 parts, 385 seconds, 3.12 MiB/s, four workers, no retries.

## Telegram storage cleanup

The admin can disable a registered media asset and request cleanup. The worker claims pending assets and verifies Telegram deletion before marking them deleted. A new movie-level **Delete movie & Telegram files** action stages all registered movie assets, then finalizes removal of movie metadata and associated import jobs after confirmed deletion. A last-copy guard remains for ordinary per-asset cleanup; movie-level deletion is an explicit exception. Do not remove the database row first: that can orphan storage messages. Previously overwritten/lost message references (such as old .bin uploads) are not discoverable by this workflow. **Do not use the destructive workflow on production data until end-to-end tests and backup/recovery are verified.**

The hosted Telegram Bot API's 50 MB upload limit applies to the older Bot API path, not this Telethon MTProto upload path. MTProto still has Telegram account, file-size and platform limits.


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

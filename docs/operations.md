# Operations runbooks

Every command assumes the repo root and a running compose stack. Times/RPO/RTO below are **not measured** — measure them in staging.

## Takedown / revoke media (fastest first)
1. Admin → Titles → the title → **Unpublish**. Effective on the next request (members, bot buttons, Mini App links).
2. Or Admin → Rights → **Revoke** (rights expiry does the same automatically: nothing to run).
3. To remove stored bytes: delete the message in the private storage channel. Verify: the bot button answers "isn't available".
Every publish/unpublish/revoke/delivery is in Admin → Audit log.

## Rotate secrets
- **Bot token:** @BotFather `/revoke`, put the new token in `.env`, `docker compose up -d bot backend`. (Stored file references stay valid; the new token must still be admin of the channel.)
- **WORKER_API_TOKEN / BOT_API_TOKEN / JWT_SIGNING_KEY:** change in `.env`, restart `backend` (and `bot` for BOT_API_TOKEN), update Colab Secrets. JWT rotation signs everyone out (they log in again silently).
- **ENCRYPTION_KEY:** set `ENCRYPTION_KEY=<new>,<old>` (first encrypts, all decrypt), restart. Old values stay readable. A re-encryption script is **not built**, so keep the old key until you re-save affected records; removing it makes old references unreadable.

## Interrupted or stuck import job
Colab disconnects need no action: the lease (default 5 min) expires and the next worker run reclaims the job (max 3 attempts, then FAILED).
Admin → Imports: **Retry** a FAILED/BLOCKED/EXPIRED job, **Cancel** one you don't want. Partial downloads restart from zero.
A job in BLOCKED_RIGHTS means rights were missing/expired/revoked at completion; fix the rights record, Retry, approve again.

## Backup and restore (PostgreSQL)
```bash
docker compose exec -T db pg_dump -U $POSTGRES_USER -Fc $POSTGRES_DB > backup_$(date +%F).dump     # run daily via cron; encrypt and copy off-host
docker compose stop backend bot
docker compose exec -T db pg_restore -U $POSTGRES_USER -d $POSTGRES_DB --clean --if-exists < backup_YYYY-MM-DD.dump
docker compose start backend bot && python -m scripts.smoke https://<api-host>
```
Test a restore on a scratch database before you need it. Backups hold encrypted references but also user data: protect them.
Media bytes live in the Telegram channel, not in the database: deleting the channel loses them.

## Disable billing / roll back
Billing is off (`BILLING_ENABLED=false`); subscriptions are not built yet.
Roll back code: redeploy the previous image/commit. If the newer release added migrations, rolling back code usually still works
(migrations are additive so far); only downgrade the schema deliberately: `docker compose exec backend alembic downgrade -1` (data loss possible).

## Watch for
`docker compose logs backend` prints one JSON line per request (id, method, path, status, ms; no query strings or tokens).
Repeated `RETRY_WAIT`/`FAILED` jobs, 5xx rates, and Admin Overview's "rights expiring in 14 days" are the signals available today;
automated alerting is not built.


## Movie-level permanent deletion (October 2026; validation required)

The admin movie detail screen has **Delete movie & Telegram files**. Confirming it calls `POST /api/v1/admin/catalog/movie/{item_id}/delete-all`, marks the movie `deleting` (no longer published), and queues registered Telegram assets for MTProto cleanup. Run the Colab worker's cleanup loop. The worker calls `POST /api/v1/worker/cleanup/claim`, deletes messages from the storage channel and calls `POST /api/v1/worker/cleanup/{asset_id}/finish` with the verified result. When every registered asset has status `deleted`, the backend finalizer removes the movie and its linked import jobs, rights, translations, favorites and collection entries.

If cleanup fails, do not manually delete database rows or the remaining Telegram references. Diagnose the worker and retry the failed cleanup deliberately. The workflow only knows Telegram message references still in the database; earlier replaced .bin messages may remain orphaned and require separate channel inspection. **This flow has not yet been validated end-to-end and must not be treated as production-safe.** Back up the database and verify Telegram permissions first. The old last-copy protection still applies to individual asset cleanup, not the explicit whole-movie delete operation.

## Parallel upload diagnostics

The Colab notebook configures four MTProto parallel workers. Look for `upload_parallel_metrics` at 30-second intervals and `upload_parallel_summary` after upload. Interpret `peak_active=4` as four simultaneous outstanding upload requests; `retries=0` means no retry was recorded. Observed performance is environment-specific and can change between runs.

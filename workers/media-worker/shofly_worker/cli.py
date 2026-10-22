import logging
import time
import httpx
from shofly_worker.client import BackendClient
from shofly_worker.config import WorkerSettings
from shofly_worker.providers import LocalDirProvider, TelegramProvider, MTProtoTelegramProvider
from shofly_worker.runner import run_until_empty

log = logging.getLogger("shofly_worker")


def build_provider(s: WorkerSettings):
    if s.provider == "telegram":
        if not (s.telegram_bot_token and s.telegram_chat_id):
            raise SystemExit("PROVIDER=telegram needs TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID")
        return TelegramProvider(s.telegram_bot_token, s.telegram_chat_id, s.max_bytes)
    if s.provider == "telegram_mtproto":
        if not (s.telegram_api_id and s.telegram_api_hash and s.telegram_bot_token and s.telegram_chat_id):
            raise SystemExit("telegram_mtproto needs Telegram API ID/hash, bot token and channel")
        return MTProtoTelegramProvider(s.telegram_api_id, s.telegram_api_hash,
                                       s.telegram_bot_token, s.telegram_chat_id,
                                       s.telegram_session, s.mtproto_max_bytes)
    if s.provider == "local":
        return LocalDirProvider(s.local_dir)
    raise SystemExit(f"unknown PROVIDER {s.provider!r} (use telegram or local)")


def loop(client, provider, settings, dl_http, max_cycles: int | None = None, sleep=time.sleep) -> int:
    """Check the queue, process everything claimable, sleep, repeat. Returns jobs processed (max_cycles is for tests)."""
    total, cycles = 0, 0
    while max_cycles is None or cycles < max_cycles:
        # Only MTProto can verify message deletion. Other providers leave requests pending.
        if isinstance(provider, MTProtoTelegramProvider):
            try:
                task = client.claim_cleanup()
            except (httpx.HTTPError, Exception) as exc:
                log.warning("cleanup_claim_failed reason=%s", type(exc).__name__)
                task = None
            if task:
                success = True
                try:
                    for ref in task["refs"]:
                        if not provider.delete_confirmed(ref):
                            success = False
                            break
                except Exception as exc:
                    log.warning("cleanup_delete_failed asset_id=%s reason=%s", task["id"], type(exc).__name__)
                    success = False
                try:
                    client.finish_cleanup(task["id"], success, None if success else "TELEGRAM_DELETE_FAILED")
                except Exception as exc:
                    log.error("cleanup_result_not_saved asset_id=%s reason=%s", task["id"], type(exc).__name__)
                if success:
                    log.info("cleanup_confirmed asset_id=%s", task["id"])
        results = run_until_empty(client, provider, settings, dl_http)
        total += len(results); cycles += 1
        if results:
            log.info("cycle %d: %s", cycles, results)
        if max_cycles is not None and cycles >= max_cycles:
            break
        sleep(settings.poll_seconds)
    return total


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    s = WorkerSettings()
    client = BackendClient(s.api_base_url, s.worker_api_token, s.worker_id)
    try:
        if not client.ping():
            raise SystemExit("backend rejected the worker token (check WORKER_API_TOKEN on both sides)")
    except httpx.HTTPError:
        raise SystemExit("cannot reach the backend (check API_BASE_URL; free hosts may need ~1 minute to wake up: retry)")
    log.info("worker %s ready (provider=%s); Ctrl+C to stop", s.worker_id, s.provider)
    try:
        loop(client, build_provider(s), s, httpx.Client(timeout=60.0))
    except KeyboardInterrupt:
        log.info("stopped; any job in progress is re-queued when its lease expires")

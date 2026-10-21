import logging
import time
import httpx
from shofly_worker.client import BackendClient
from shofly_worker.config import WorkerSettings
from shofly_worker.providers import LocalDirProvider, TelegramProvider
from shofly_worker.runner import run_until_empty

log = logging.getLogger("shofly_worker")


def build_provider(s: WorkerSettings):
    if s.provider == "telegram":
        if not (s.telegram_bot_token and s.telegram_chat_id):
            raise SystemExit("PROVIDER=telegram needs TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID")
        return TelegramProvider(s.telegram_bot_token, s.telegram_chat_id, s.max_bytes)
    if s.provider == "local":
        return LocalDirProvider(s.local_dir)
    raise SystemExit(f"unknown PROVIDER {s.provider!r} (use telegram or local)")


def loop(client, provider, settings, dl_http, max_cycles: int | None = None, sleep=time.sleep) -> int:
    """Check the queue, process everything claimable, sleep, repeat. Returns jobs processed (max_cycles is for tests)."""
    total, cycles = 0, 0
    while max_cycles is None or cycles < max_cycles:
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

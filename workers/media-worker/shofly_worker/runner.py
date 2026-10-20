import logging
import shutil
import threading
from pathlib import Path
import httpx
from shofly_worker.client import ApiError, BackendClient
from shofly_worker.downloader import download
from shofly_worker.errors import LeaseLost, SourceExpired, WorkerError
from shofly_worker.probe import probe

log = logging.getLogger("shofly_worker")


class Heartbeat(threading.Thread):
    def __init__(self, client: BackendClient, jid: str, every: float):
        super().__init__(daemon=True)
        self.client, self.jid, self.every = client, jid, every
        self.stop_evt, self.lost = threading.Event(), threading.Event()

    def run(self):
        while not self.stop_evt.wait(self.every):
            try:
                self.client.heartbeat(self.jid)
            except LeaseLost:
                self.lost.set(); return
            except Exception:  # transient network blip: lease may still be valid, keep trying
                log.warning("heartbeat failed for job %s", self.jid)


def process_one(client: BackendClient, provider, settings, dl_http: httpx.Client, resolver=None, probe_fn=probe) -> str | None:
    """Claim and process one job. Returns the outcome label, or None if the queue is empty.
    Only a successful /complete marks a job done; any crash/disconnect leaves it to lease expiry."""
    job = client.claim()
    if job is None:
        return None
    jid, tmp = job["id"], Path(settings.tmp_dir) / job["id"]
    hb = Heartbeat(client, jid, settings.heartbeat_seconds); hb.start()
    ref = None

    def check():
        if hb.lost.is_set():
            raise LeaseLost()

    try:
        check(); client.progress(jid, "DOWNLOADING", 5)
        hosts = {h.strip().lower() for h in settings.allowed_hosts.split(",") if h.strip()} or None
        size, sha = download(job["source_ref"], tmp / "source.bin", dl_http, settings.max_bytes, settings.download_timeout,
                             hosts, resolver, check)
        check(); client.progress(jid, "PROBING", 40)
        info = probe_fn(tmp / "source.bin")
        check(); client.progress(jid, "UPLOADING", 60)
        ref = provider.upload(tmp / "source.bin", info)
        check(); client.progress(jid, "VERIFYING", 85)
        if not provider.verify(ref, size):
            raise WorkerError("VERIFY_FAILED", "Uploaded file could not be verified.", True)
        check()
        try:
            client.complete(jid, verified=True, provider=provider.name, provider_ref=ref, size_bytes=size, checksum_sha256=sha, **info)
        except ApiError as e:
            if e.code == "BLOCKED_RIGHTS":
                provider.delete(ref)  # never leave unlicensed media in storage
                return "BLOCKED_RIGHTS"
            raise
        return "COMPLETED"
    except LeaseLost:
        if ref: provider.delete(ref)  # someone else owns the job now; our upload is an orphan
        return "LEASE_LOST"
    except WorkerError as e:
        if ref: provider.delete(ref)
        _report(client, jid, e.code, e.message, e.retryable)
        return e.code
    except Exception:  # unexpected: generic safe message only, details stay in local logs
        log.exception("job %s crashed", jid)
        if ref: provider.delete(ref)
        _report(client, jid, "UNEXPECTED", "Unexpected worker error.", True)
        return "UNEXPECTED"
    finally:
        hb.stop_evt.set()
        shutil.rmtree(tmp, ignore_errors=True)


def _report(client, jid, code, msg, retryable):
    try:
        client.fail(jid, code, msg, retryable)
    except (LeaseLost, ApiError, httpx.HTTPError):
        pass  # lease will expire and the backend will reclaim it


def run_until_empty(client, provider, settings, dl_http, max_jobs: int = 100, **kw) -> list[str]:
    results = []
    for _ in range(max_jobs):
        out = process_one(client, provider, settings, dl_http, **kw)
        if out is None:
            break
        results.append(out)
    return results

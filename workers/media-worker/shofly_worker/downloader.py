import hashlib
import time
from pathlib import Path
from urllib.parse import urljoin
import httpx
from shofly_worker.errors import SourceExpired, WorkerError
from shofly_worker.ssrf import UnsafeURL, check_url


def download(url: str, dest: Path, http: httpx.Client, max_bytes: int, timeout: float,
             allowed_hosts: set[str] | None = None, resolver=None, check=lambda: None) -> tuple[int, str]:
    """Stream to disk with size/time limits. Redirects are followed manually so each hop is SSRF-checked.
    `check()` runs per chunk and may raise LeaseLost. Messages never contain the URL."""
    kw = {"resolver": resolver} if resolver else {}
    deadline = time.monotonic() + timeout
    for _ in range(6):
        try:
            check_url(url, allowed_hosts, **kw)
        except UnsafeURL:
            raise WorkerError("UNSAFE_SOURCE", "Source failed safety checks.", False)
        try:
            with http.stream("GET", url, follow_redirects=False) as r:
                if r.status_code in (301, 302, 303, 307, 308):
                    loc = r.headers.get("location")
                    if not loc:
                        raise WorkerError("BAD_REDIRECT", "Redirect without location.", False)
                    url = urljoin(url, loc)
                    continue
                if r.status_code in (404, 410):
                    raise SourceExpired()
                if r.status_code >= 400:
                    raise WorkerError("DOWNLOAD_HTTP_ERROR", f"Source returned HTTP {r.status_code}.", r.status_code >= 500 or r.status_code == 429)
                declared = int(r.headers.get("content-length", 0) or 0)
                if declared > max_bytes:
                    raise WorkerError("FILE_TOO_LARGE", "File exceeds the configured size limit.", False)
                h, total = hashlib.sha256(), 0
                dest.parent.mkdir(parents=True, exist_ok=True)
                with open(dest, "wb") as f:
                    for chunk in r.iter_bytes(1 << 20):
                        total += len(chunk)
                        if total > max_bytes:
                            raise WorkerError("FILE_TOO_LARGE", "File exceeds the configured size limit.", False)
                        if time.monotonic() > deadline:
                            raise WorkerError("DOWNLOAD_TIMEOUT", "Download took too long.", True)
                        check()
                        h.update(chunk); f.write(chunk)
                if total == 0:
                    raise WorkerError("EMPTY_FILE", "Source returned no data.", False)
                return total, h.hexdigest()
        except httpx.HTTPError:
            raise WorkerError("DOWNLOAD_NETWORK_ERROR", "Network error while downloading.", True)
    raise WorkerError("TOO_MANY_REDIRECTS", "Too many redirects.", False)

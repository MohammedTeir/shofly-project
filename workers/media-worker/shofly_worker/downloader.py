import hashlib
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
import logging
import time
from pathlib import Path
from urllib.parse import urljoin
import httpx
from shofly_worker.progress import TransferProgress
from shofly_worker.errors import SourceExpired, WorkerError
from shofly_worker.ssrf import UnsafeURL, check_url


def download(url: str, dest: Path, http: httpx.Client, max_bytes: int, timeout: float,
             allowed_hosts: set[str] | None = None, resolver=None, check=lambda: None) -> tuple[int, str]:
    """Stream to disk with size/time limits. Redirects are followed manually so each hop is SSRF-checked.
    `check()` runs per chunk and may raise LeaseLost. Messages never contain the URL."""
    kw = {"resolver": resolver} if resolver else {}
    deadline = time.monotonic() + timeout
    progress = TransferProgress('download')
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
                progress.start(declared if declared > 0 else None)
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
                        progress.update(total)
                if total == 0:
                    raise WorkerError("EMPTY_FILE", "Source returned no data.", False)
                progress.finish(total)
                return total, h.hexdigest()
        except httpx.HTTPError:
            raise WorkerError("DOWNLOAD_NETWORK_ERROR", "Network error while downloading.", True)
    raise WorkerError("TOO_MANY_REDIRECTS", "Too many redirects.", False)


def download_parallel(url: str, dest: Path, http: httpx.Client, max_bytes: int, timeout: float,
                      allowed_hosts: set[str] | None = None, resolver=None, check=lambda: None,
                      connections: int = 8, chunk_size: int = 8 * 1024 * 1024) -> tuple[int, str]:
    """Parallel bounded HTTP ranges; transparently use streaming download if ranges unsupported."""
    if not 1 <= connections <= 32 or chunk_size < 1024 * 1024:
        raise ValueError("Invalid HTTPX parallel settings")
    if connections == 1:
        return download(url, dest, http, max_bytes, timeout, allowed_hosts, resolver, check)
    kw = {"resolver": resolver} if resolver else {}
    deadline = time.monotonic() + timeout

    # Resolve redirects using a small ranged GET; validate every hop.
    current = url
    for _ in range(6):
        try:
            check_url(current, allowed_hosts, **kw)
        except UnsafeURL:
            raise WorkerError("UNSAFE_SOURCE", "Source failed safety checks.", False)
        try:
            with http.stream("GET", current, headers={"Range": "bytes=0-0", "Accept-Encoding": "identity"},
                             follow_redirects=False) as resp:
                if resp.status_code in (301, 302, 303, 307, 308):
                    loc = resp.headers.get("location")
                    if not loc:
                        raise WorkerError("BAD_REDIRECT", "Redirect without location.", False)
                    current = urljoin(current, loc)
                    continue
                if resp.status_code in (404, 410):
                    raise SourceExpired()
                if resp.status_code >= 400 and resp.status_code != 416:
                    raise WorkerError("DOWNLOAD_HTTP_ERROR", f"Source returned HTTP {resp.status_code}.", resp.status_code >= 500 or resp.status_code == 429)
                match = re.fullmatch(r"bytes 0-0/(\d+)", resp.headers.get("content-range", "").strip())
                if resp.status_code != 206 or not match or resp.headers.get("content-encoding", "identity").lower() != "identity":
                    return download(url, dest, http, max_bytes, timeout, allowed_hosts, resolver, check)
                size = int(match.group(1))
                if size > max_bytes:
                    raise WorkerError("FILE_TOO_LARGE", "File exceeds the configured size limit.", False)
                if size <= 0:
                    raise WorkerError("EMPTY_FILE", "Source returned no data.", False)
                etag = resp.headers.get("etag")
                break
        except httpx.HTTPError:
            raise WorkerError("DOWNLOAD_NETWORK_ERROR", "Network error while downloading.", True)
    else:
        raise WorkerError("TOO_MANY_REDIRECTS", "Too many redirects.", False)

    # Each worker owns a disjoint range and its own file handle.
    dest.parent.mkdir(parents=True, exist_ok=True)
    temp = dest.with_name(dest.name + ".parallel")
    ranges = [(start, min(start + chunk_size, size) - 1) for start in range(0, size, chunk_size)]
    lock = Lock()
    completed = 0
    progress = TransferProgress("download")
    progress.start(size)

    def part(bounds):
        nonlocal completed
        start, end = bounds
        for attempt in range(3):
            check()
            if time.monotonic() >= deadline:
                raise WorkerError("DOWNLOAD_TIMEOUT", "Download took too long.", True)
            headers = {"Range": f"bytes={start}-{end}", "Accept-Encoding": "identity"}
            if etag:
                headers["If-Range"] = etag
            try:
                with http.stream("GET", current, headers=headers, follow_redirects=False) as response:
                    expected = f"bytes {start}-{end}/{size}"
                    if response.status_code != 206 or response.headers.get("content-range", "").strip() != expected:
                        raise WorkerError("INVALID_RANGE", "Source did not honor the requested byte range.", False)
                    if response.headers.get("content-encoding", "identity").lower() != "identity":
                        raise WorkerError("INVALID_RANGE", "Compressed range response is not supported.", False)
                    count = 0
                    with temp.open("r+b") as out:
                        out.seek(start)
                        for data in response.iter_bytes(1024 * 1024):
                            check()
                            if time.monotonic() >= deadline:
                                raise WorkerError("DOWNLOAD_TIMEOUT", "Download took too long.", True)
                            count += len(data)
                            if count > end - start + 1:
                                raise WorkerError("INVALID_RANGE", "Range response exceeded expected size.", False)
                            out.write(data)
                    if count != end - start + 1:
                        raise WorkerError("INCOMPLETE_RANGE", "Incomplete range response.", True)
                with lock:
                    completed += count
                    progress.update(completed)
                return
            except httpx.HTTPError:
                if attempt == 2:
                    raise WorkerError("DOWNLOAD_NETWORK_ERROR", "Network error while downloading.", True)
            except WorkerError as exc:
                if not exc.retryable or attempt == 2:
                    raise
    try:
        with temp.open("wb") as out:
            out.truncate(size)
        with ThreadPoolExecutor(max_workers=connections) as pool:
            futures = [pool.submit(part, bounds) for bounds in ranges]
            for future in as_completed(futures):
                future.result()
        digest = hashlib.sha256()
        with temp.open("rb") as inp:
            for data in iter(lambda: inp.read(1024 * 1024), b""):
                check()
                digest.update(data)
        temp.replace(dest)
        progress.finish(size)
        logging.getLogger("shofly_worker").info("httpx_parallel_summary bytes=%d connections=%d chunks=%d", size, connections, len(ranges))
        return size, digest.hexdigest()
    finally:
        temp.unlink(missing_ok=True)

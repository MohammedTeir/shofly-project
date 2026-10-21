"""Optional parallel aria2c transfer for explicitly allowlisted HTTPS sources.

Redirects are disabled. HTTPX remains the default for arbitrary URLs.
Supports retries and partial resume; persistence depends on a mounted directory.
"""
import hashlib
import os
import logging
import re
import subprocess
import time
from pathlib import Path

from shofly_worker.errors import WorkerError

log = logging.getLogger("shofly_worker")


def _safe_aria2_error(output: str) -> str:
    """Keep aria2 error codes, not source URLs, query tokens or response bodies."""
    codes = re.findall(r"errorCode\s*=\s*(\d+)", output, flags=re.IGNORECASE)
    return ",".join(dict.fromkeys(codes))[:80] if codes else "unknown"

from shofly_worker.ssrf import UnsafeURL, check_url


def download_aria2(url: str, dest: Path, max_bytes: int, timeout: float,
                   allowed_hosts: set[str] | None, check=lambda: None,
                   connections: int = 4, retries: int = 3) -> tuple[int, str]:
    if not allowed_hosts:
        raise WorkerError("ARIA2_ALLOWLIST_REQUIRED", "aria2c requires explicitly allowed hosts.", False)
    try:
        check_url(url, allowed_hosts)
    except UnsafeURL:
        raise WorkerError("UNSAFE_SOURCE", "Source failed safety checks.", False)
    if not 1 <= connections <= 8 or not 1 <= retries <= 5:
        raise WorkerError("INVALID_DOWNLOAD_CONFIG", "Invalid transfer settings.", False)
    dest.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "aria2c", "--no-conf=true", "--allow-overwrite=true",
        "--auto-file-renaming=false", "--max-redirect=0",
        "--max-connection-per-server=" + str(connections), "--split=" + str(connections),
        "--min-split-size=1M", "--continue=true",
        "--retry-wait=3", "--max-tries=" + str(retries),
        "--file-allocation=none", "--console-log-level=error",
        "--summary-interval=0",
        "--no-proxy=*", "--max-file-size=" + str(max_bytes),
        "--dir=" + str(dest.parent), "--out=" + dest.name, url,
    ]
    env = dict(os.environ)
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        env.pop(key, None)
    try:
        proc = subprocess.Popen(command, stdout=subprocess.DEVNULL,
                                stderr=subprocess.PIPE, env=env)
    except FileNotFoundError:
        raise WorkerError("ARIA2_UNAVAILABLE", "aria2c is not installed.", False)
    deadline = time.monotonic() + timeout
    try:
        while proc.poll() is None:
            check()
            if time.monotonic() > deadline:
                raise WorkerError("DOWNLOAD_TIMEOUT", "Download timed out.", True)
            if dest.exists() and dest.stat().st_size > max_bytes:
                raise WorkerError("FILE_TOO_LARGE", "File exceeds the configured size limit.", False)
            time.sleep(0.5)
        if proc.returncode:
            diagnostic = proc.stderr.read(65536).decode("utf-8", errors="replace") if proc.stderr else ""
            log.warning("aria2c_failed exit_code=%s aria2_error_codes=%s", proc.returncode, _safe_aria2_error(diagnostic))
            raise WorkerError("ARIA2_DOWNLOAD_FAILED", "aria2c download failed.", True)
        if not dest.is_file() or dest.stat().st_size == 0:
            raise WorkerError("EMPTY_FILE", "Source returned no data.", False)
        size = dest.stat().st_size
        if size > max_bytes:
            raise WorkerError("FILE_TOO_LARGE", "File exceeds the configured size limit.", False)
        digest = hashlib.sha256()
        with dest.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                check()
                digest.update(chunk)
        return size, digest.hexdigest()
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        if proc.stderr:
            proc.stderr.close()
        # Preserve aria2 control data for retries within this worker attempt.
        # The runner owns temp directory cleanup; phase 2 will persist partial files.

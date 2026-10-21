"""Optional aria2c transfer for explicitly allowlisted HTTPS sources.

Redirects are disabled. HTTPX remains the default for arbitrary URLs.
This module intentionally does not claim durable resume support.
"""
import hashlib
import os
import subprocess
import time
from pathlib import Path

from shofly_worker.errors import WorkerError
from shofly_worker.ssrf import UnsafeURL, check_url


def download_aria2(url: str, dest: Path, max_bytes: int, timeout: float,
                   allowed_hosts: set[str] | None, check=lambda: None) -> tuple[int, str]:
    if not allowed_hosts:
        raise WorkerError("ARIA2_ALLOWLIST_REQUIRED", "aria2c requires explicitly allowed hosts.", False)
    try:
        check_url(url, allowed_hosts)
    except UnsafeURL:
        raise WorkerError("UNSAFE_SOURCE", "Source failed safety checks.", False)
    dest.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "aria2c", "--no-conf=true", "--allow-overwrite=true",
        "--auto-file-renaming=false", "--max-redirect=0",
        "--max-connection-per-server=1", "--split=1",
        "--file-allocation=none", "--console-log-level=error",
        "--summary-interval=0", "--max-tries=1",
        "--no-proxy=*", "--max-file-size=" + str(max_bytes),
        "--dir=" + str(dest.parent), "--out=" + dest.name, url,
    ]
    env = dict(os.environ)
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        env.pop(key, None)
    try:
        proc = subprocess.Popen(command, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, env=env)
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
        dest.with_name(dest.name + ".aria2").unlink(missing_ok=True)

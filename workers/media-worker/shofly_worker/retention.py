"""Bounded cleanup for Shofly-owned persistent transfer directories."""
import json
import logging
import shutil
import time
import uuid
from pathlib import Path

log = logging.getLogger("shofly_worker")
FINAL_TTL_SECONDS = 48 * 3600
ORPHAN_TTL_SECONDS = 7 * 24 * 3600


def _root(path: str) -> Path:
    root = Path(path).expanduser().resolve(strict=True)
    if not root.is_dir() or root.is_symlink() or str(root) in ("/", "/content", "/content/drive", "/content/drive/MyDrive"):
        raise ValueError("Persistent directory must be an existing dedicated Shofly folder.")
    return root


def job_dir(path: str, jid: str) -> Path:
    root = _root(path)
    # Job IDs are UUIDs, never paths.
    if str(uuid.UUID(jid)) != jid.lower():
        raise ValueError("Invalid job identifier.")
    return root / jid


def mark_final(folder: Path) -> None:
    marker = folder / "retention.json"
    marker.write_text(json.dumps({"final_at": time.time()}))


def cleanup(path: str, now: float | None = None) -> int:
    root = _root(path)
    now = time.time() if now is None else now
    removed = 0
    for child in root.iterdir():
        if child.is_symlink() or not child.is_dir():
            continue
        try:
            if str(uuid.UUID(child.name)) != child.name.lower():
                continue
            meta = child / "retention.json"
            if meta.is_symlink():
                continue
            if meta.exists():
                final_at = float(json.loads(meta.read_text())["final_at"])
                expired = 0 <= final_at <= now - FINAL_TTL_SECONDS
            else:
                # Crashed sessions may leave a job without a final marker.
                # Seven-day grace prevents premature removal of recent transfers.
                expired = child.stat().st_mtime <= now - ORPHAN_TTL_SECONDS
            if expired:
                shutil.rmtree(child)
                removed += 1
        except (OSError, ValueError, KeyError, TypeError):
            log.warning("retention_cleanup_skipped folder=%s", child.name)
    return removed

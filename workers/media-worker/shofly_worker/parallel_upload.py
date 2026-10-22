"""Parallel MTProto part uploads using bounded concurrent requests.

Requests share the authenticated Telethon client; concurrency does not promise
eight independent TCP sockets or eightfold throughput.
"""
import asyncio
import math
import logging
import time
import secrets
from pathlib import Path

from telethon import types
from telethon.tl.functions.upload import SaveBigFilePartRequest, SaveFilePartRequest

from shofly_worker.progress import TransferProgress

PART_SIZE = 512 * 1024
BIG_FILE_THRESHOLD = 10 * 1024 * 1024
log = logging.getLogger('shofly_worker')


async def upload_parallel(client, path: Path, workers: int = 4, retries: int = 2):
    clients = list(client) if isinstance(client, (list, tuple)) else [client]
    if not clients or len(clients) > workers:
        raise ValueError("connection count must be between 1 and workers")
    if not 1 <= workers <= 8:
        raise ValueError("workers must be between 1 and 8")
    size = path.stat().st_size
    if not size:
        raise ValueError("cannot upload an empty file")
    parts = math.ceil(size / PART_SIZE)
    if parts > 4000:
        raise ValueError("Telegram upload part limit exceeded")
    file_id = secrets.randbits(63)
    big = size > BIG_FILE_THRESHOLD
    progress = TransferProgress("upload")
    progress.start(size)
    uploaded = 0
    started = time.monotonic()
    last_report = started
    last_bytes = 0
    active = peak = attempts = retried = 0
    latency = 0.0
    lock = asyncio.Lock()
    queue = asyncio.Queue()
    for index in range(parts):
        queue.put_nowait(index)

    async def worker(connection):
        nonlocal uploaded, last_report, last_bytes, active, peak, attempts, retried, latency
        with path.open("rb") as stream:
            while True:
                try:
                    index = queue.get_nowait()
                except asyncio.QueueEmpty:
                    return
                try:
                    stream.seek(index * PART_SIZE)
                    data = stream.read(PART_SIZE)
                    if not data:
                        raise IOError("Unexpected end of upload file")
                    request = (
                        SaveBigFilePartRequest(file_id, index, parts, data)
                        if big else SaveFilePartRequest(file_id, index, data)
                    )
                    for attempt in range(retries + 1):
                        active += 1
                        peak = max(peak, active)
                        t0 = time.monotonic()
                        try:
                            accepted = await connection(request)
                            if not accepted:
                                raise RuntimeError("Telegram rejected upload part")
                            break
                        except (OSError, asyncio.TimeoutError):
                            if attempt == retries:
                                raise
                            retried += 1
                            await asyncio.sleep(min(2 ** attempt, 4))
                        finally:
                            attempts += 1
                            latency += time.monotonic() - t0
                            active -= 1
                    async with lock:
                        uploaded += len(data)
                        progress.update(uploaded)
                        now = time.monotonic()
                        if now - last_report >= 30:
                            log.info('upload_parallel_metrics window_mb_s=%.2f active=%d peak_active=%d requests=%d retries=%d avg_request_ms=%.0f', (uploaded-last_bytes)/1048576/(now-last_report), active, peak, attempts, retried, 1000*latency/max(attempts,1))
                            last_report, last_bytes = now, uploaded
                finally:
                    queue.task_done()

    tasks = [asyncio.create_task(worker(clients[i % len(clients)])) for i in range(min(workers, parts))]
    try:
        await asyncio.gather(*tasks)
    except BaseException:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise
    if uploaded != size:
        raise RuntimeError("Upload byte count mismatch")
    progress.finish(uploaded)
    log.info('upload_parallel_summary workers=%d connections=%d parts=%d elapsed_s=%.1f avg_mb_s=%.2f peak_active=%d requests=%d retries=%d avg_request_ms=%.0f', workers, len(clients), parts, time.monotonic()-started, size/1048576/max(time.monotonic()-started,0.001), peak, attempts, retried, 1000*latency/max(attempts,1))
    if big:
        return types.InputFileBig(file_id, parts, path.name)
    import hashlib
    digest = hashlib.md5(usedforsecurity=False)
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return types.InputFile(file_id, parts, path.name, digest.hexdigest())

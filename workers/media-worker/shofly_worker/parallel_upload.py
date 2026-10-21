"""Parallel MTProto part uploads using bounded concurrent requests.

Requests share the authenticated Telethon client; concurrency does not promise
eight independent TCP sockets or eightfold throughput.
"""
import asyncio
import math
import secrets
from pathlib import Path

from telethon import types
from telethon.tl.functions.upload import SaveBigFilePartRequest, SaveFilePartRequest

from shofly_worker.progress import TransferProgress

PART_SIZE = 512 * 1024
BIG_FILE_THRESHOLD = 10 * 1024 * 1024


async def upload_parallel(client, path: Path, workers: int = 8, retries: int = 2):
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
    lock = asyncio.Lock()
    queue = asyncio.Queue()
    for index in range(parts):
        queue.put_nowait(index)

    async def worker():
        nonlocal uploaded
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
                        try:
                            accepted = await client(request)
                            if not accepted:
                                raise RuntimeError("Telegram rejected upload part")
                            break
                        except (OSError, asyncio.TimeoutError):
                            if attempt == retries:
                                raise
                            await asyncio.sleep(min(2 ** attempt, 4))
                    async with lock:
                        uploaded += len(data)
                        progress.update(uploaded)
                finally:
                    queue.task_done()

    tasks = [asyncio.create_task(worker()) for _ in range(min(workers, parts))]
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
    if big:
        return types.InputFileBig(file_id, parts, path.name)
    import hashlib
    digest = hashlib.md5(usedforsecurity=False)
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return types.InputFile(file_id, parts, path.name, digest.hexdigest())

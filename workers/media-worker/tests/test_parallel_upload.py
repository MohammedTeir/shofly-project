"""Unit tests for MTProto parallel upload; no network access required."""
import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest
from telethon import types
from telethon.tl.functions.upload import SaveFilePartRequest, SaveBigFilePartRequest

from shofly_worker.parallel_upload import PART_SIZE, upload_parallel


class FakeClient:
    def __init__(self, fail_part=None):
        self.parts = {}
        self.active = 0
        self.peak = 0
        self.fail_part = fail_part

    async def __call__(self, request):
        self.active += 1
        self.peak = max(self.peak, self.active)
        try:
            await asyncio.sleep(0.001)
            if request.file_part == self.fail_part:
                raise RuntimeError("part failed")
            self.parts[request.file_part] = bytes(request.bytes)
            return True
        finally:
            self.active -= 1


def test_parallel_small_file_roundtrip(tmp_path):
    payload = b"x" * (PART_SIZE * 3 + 17)
    path = tmp_path / "test.bin"
    path.write_bytes(payload)
    client = FakeClient()
    result = asyncio.run(upload_parallel(client, path, workers=8))
    assert isinstance(result, types.InputFile)
    assert result.parts == 4
    assert client.peak > 1
    assert b"".join(client.parts[i] for i in range(4)) == payload


def test_parallel_big_file_receipt(tmp_path):
    path = tmp_path / "big.bin"
    path.write_bytes(b"z" * (10 * 1024 * 1024 + 1))
    client = FakeClient()
    result = asyncio.run(upload_parallel(client, path, workers=8))
    assert isinstance(result, types.InputFileBig)
    assert result.parts == 21
    assert b"".join(client.parts[i] for i in range(result.parts)) == path.read_bytes()


def test_parallel_error_propagates(tmp_path):
    path = tmp_path / "fail.bin"
    path.write_bytes(b"x" * (PART_SIZE * 2))
    with pytest.raises(RuntimeError, match="part failed"):
        asyncio.run(upload_parallel(FakeClient(fail_part=1), path, workers=8))


def test_invalid_worker_count(tmp_path):
    path = tmp_path / "test.bin"
    path.write_bytes(b"hello")
    with pytest.raises(ValueError, match="workers"):
        asyncio.run(upload_parallel(FakeClient(), path, workers=33))


def test_four_connections_with_sixteen_workers(tmp_path):
    payload = b"x" * (PART_SIZE * 17 + 31)
    path = tmp_path / "multi.bin"
    path.write_bytes(payload)
    clients = [FakeClient() for _ in range(4)]
    result = asyncio.run(upload_parallel(clients, path, workers=16))
    assert result.parts == 18
    assert all(c.parts for c in clients)
    merged = {}
    for c in clients:
        merged.update(c.parts)
    assert b"".join(merged[i] for i in range(result.parts)) == payload


def test_more_connections_than_workers_rejected(tmp_path):
    path = tmp_path / "test.bin"
    path.write_bytes(b"hello")
    with pytest.raises(ValueError, match="connections"):
        asyncio.run(upload_parallel([FakeClient() for _ in range(5)], path, workers=4))

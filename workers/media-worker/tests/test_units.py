import json
import subprocess
from pathlib import Path
import httpx
import pytest
from shofly_worker.downloader import download
from shofly_worker.errors import LeaseLost, SourceExpired, WorkerError
from shofly_worker.probe import probe
from shofly_worker.providers import LocalDirProvider, TelegramProvider
from shofly_worker.ssrf import UnsafeURL, check_url
from helpers import PUBLIC

URL = "https://media.example/v.mp4"


def dl(handler, tmp_path, **kw):
    http = httpx.Client(transport=httpx.MockTransport(handler))
    return download(URL, tmp_path / "f.bin", http, kw.pop("max_bytes", 10**6), kw.pop("timeout", 30), resolver=PUBLIC, **kw)


def test_ssrf_blocks_private_and_non_https():
    for u, ip in [("https://a.example/x", "127.0.0.1"), ("https://a.example/x", "169.254.169.254"), ("https://a.example/x", "10.1.1.1")]:
        with pytest.raises(UnsafeURL):
            check_url(u, resolver=lambda h, p, type=None, ip=ip: [(2, 1, 6, "", (ip, 443))])
    with pytest.raises(UnsafeURL):
        check_url("http://a.example/x", resolver=PUBLIC)


def test_download_ok_with_checksum(tmp_path):
    import hashlib
    size, sha = dl(lambda r: httpx.Response(200, content=b"hello" * 1000), tmp_path)
    assert size == 5000 and sha == hashlib.sha256(b"hello" * 1000).hexdigest() and (tmp_path / "f.bin").stat().st_size == 5000


def test_download_limits(tmp_path):
    with pytest.raises(WorkerError) as e:
        dl(lambda r: httpx.Response(200, content=b"x" * 5000), tmp_path, max_bytes=1000)
    assert e.value.code == "FILE_TOO_LARGE" and not e.value.retryable
    with pytest.raises(WorkerError) as e:  # declared size rejected before any bytes are read
        dl(lambda r: httpx.Response(200, headers={"content-length": "999999999"}, content=b"x"), tmp_path, max_bytes=1000)
    assert e.value.code == "FILE_TOO_LARGE"


def test_download_status_handling(tmp_path):
    with pytest.raises(SourceExpired):
        dl(lambda r: httpx.Response(404), tmp_path)
    with pytest.raises(WorkerError) as e:
        dl(lambda r: httpx.Response(503), tmp_path)
    assert e.value.retryable
    with pytest.raises(WorkerError) as e:
        dl(lambda r: httpx.Response(403), tmp_path)
    assert not e.value.retryable


def test_redirect_to_private_address_is_blocked_and_never_fetched(tmp_path):
    calls = []

    def handler(req):
        calls.append(str(req.url))
        return httpx.Response(302, headers={"location": "https://internal.example/secret"})
    http = httpx.Client(transport=httpx.MockTransport(handler))
    res = lambda h, p, type=None: [(2, 1, 6, "", ("93.184.216.34" if h == "media.example" else "10.0.0.7", 443))]
    with pytest.raises(WorkerError) as e:
        download(URL, tmp_path / "f", http, 10**6, 30, resolver=res)
    assert e.value.code == "UNSAFE_SOURCE" and calls == [URL]


def test_lease_loss_aborts_download(tmp_path):
    def boom(): raise LeaseLost()
    with pytest.raises(LeaseLost):
        dl(lambda r: httpx.Response(200, content=b"x" * 100), tmp_path, check=boom)


def fake_run(stdout="", code=0):
    return lambda *a, **k: subprocess.CompletedProcess(a, code, stdout, "")


def test_probe_parses_and_rejects(tmp_path):
    ok = json.dumps({"format": {"duration": "61.6"}, "streams": [{"codec_type": "video", "codec_name": "h264", "height": 1080},
                                                                  {"codec_type": "audio", "tags": {"language": "ara"}}]})
    assert probe(tmp_path, fake_run(ok)) == {"duration_sec": 62, "codec": "h264", "quality": "1080p", "audio_language": "ara"}
    with pytest.raises(WorkerError) as e:
        probe(tmp_path, fake_run(json.dumps({"format": {"duration": "5"}, "streams": [{"codec_type": "audio"}]})))
    assert e.value.code == "NOT_VIDEO"
    with pytest.raises(WorkerError) as e:
        probe(tmp_path, fake_run("", 1))
    assert e.value.code == "PROBE_FAILED" and not e.value.retryable
    def missing(*a, **k): raise FileNotFoundError
    with pytest.raises(WorkerError) as e:
        probe(tmp_path, missing)
    assert e.value.code == "PROBE_UNAVAILABLE" and e.value.retryable


def test_local_provider_roundtrip(tmp_path):
    p = LocalDirProvider(str(tmp_path / "s")); src = tmp_path / "a.mp4"; src.write_bytes(b"12345")
    ref = p.upload(src, {}); assert p.verify(ref, 5) and not p.verify(ref, 6)
    p.delete(ref); assert not p.verify(ref, 5)


def test_telegram_provider_with_mock_api(tmp_path):
    src = tmp_path / "a.mp4"; src.write_bytes(b"x" * 100)
    def handler(req):
        if req.url.path.endswith("sendDocument"):
            return httpx.Response(200, json={"ok": True, "result": {"message_id": 7, "chat": {"id": -100}, "document": {"file_id": "FID", "file_size": 100}}})
        if req.url.path.endswith("getFile"):
            return httpx.Response(200, json={"ok": True, "result": {"file_size": 100}})
        return httpx.Response(200, json={"ok": True})
    p = TelegramProvider("T", "-100", http=httpx.Client(transport=httpx.MockTransport(handler)))
    ref = p.upload(src, {}); assert ref == "-100:7:FID" and p.verify(ref, 100) and not p.verify(ref, 99)
    with pytest.raises(WorkerError) as e:
        TelegramProvider("T", "-100", max_bytes=10, http=httpx.Client(transport=httpx.MockTransport(handler))).upload(src, {})
    assert e.value.code == "FILE_TOO_LARGE" and not e.value.retryable


def test_userdrive_8443_worker_exception_and_other_hosts_blocked():
    check_url("https://d900.userdrive.org:8443/d/example", resolver=PUBLIC)
    with pytest.raises(UnsafeURL):
        check_url("https://other.userdrive.org:8443/d/example", resolver=PUBLIC)

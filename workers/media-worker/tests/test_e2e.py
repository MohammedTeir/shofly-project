"""Worker <-> real backend (in-process, SQLite). Only the media source and storage are fake."""
import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
import httpx
from app.core.crypto import encrypt
from app.models import ContentRight, ImportJob, MediaAsset, Movie, User
from shofly_worker.client import BackendClient
from shofly_worker.config import WorkerSettings
from shofly_worker.providers import LocalDirProvider
from shofly_worker.runner import run_until_empty, process_one
from helpers import PUBLIC

NOW = datetime.now(timezone.utc)
BYTES = b"fake-video-bytes" * 500
INFO = lambda p: {"duration_sec": 60, "codec": "h264", "quality": "1080p", "audio_language": "ara"}


def seed(db, n=1, rights=True):
    u = db.query(User).first() or User(telegram_id=1, preferred_language="en"); db.add(u); db.flush()
    jobs = []
    for i in range(n):
        m = Movie(original_title=f"Owned {i}", status="draft"); db.add(m); db.flush()
        j = ImportJob(source_type="direct_url", source_ref_encrypted=encrypt(f"https://media.example/{i}.mp4"), requested_by=u.id,
                      status="READY", candidate_kind="movie", target_id=m.id, idempotency_key=uuid.uuid4().hex); db.add(j)
        if rights:
            db.add(ContentRight(content_kind="movie", content_id=m.id, license_type="owned", proof_ref_encrypted=encrypt("p"),
                                telegram_allowed=True, territories=["ALL"], valid_from=NOW - timedelta(days=1),
                                valid_until=NOW + timedelta(days=5), review_status="APPROVED"))
        jobs.append(j)
    db.commit()
    return jobs


def rig(api, tmp_path, provider=None, handler=None):
    s = WorkerSettings(api_base_url="http://x", worker_api_token="worker-secret-token", worker_id="worker-test1",
                       tmp_dir=str(tmp_path / "tmp"), local_dir=str(tmp_path / "store"), heartbeat_seconds=999)
    client = BackendClient("http://x", s.worker_api_token, s.worker_id, http=api)
    dl = httpx.Client(transport=httpx.MockTransport(handler or (lambda r: httpx.Response(200, content=BYTES))))
    return s, client, provider or LocalDirProvider(s.local_dir), dl


def fresh(db, jid):
    db.expire_all(); return db.get(ImportJob, jid)


def test_full_success_attaches_one_verified_asset_and_cleans_up(api, db, tmp_path):
    (j,) = seed(db); s, c, p, dl = rig(api, tmp_path)
    assert process_one(c, p, s, dl, resolver=PUBLIC, probe_fn=INFO) == "COMPLETED"
    a = db.query(MediaAsset).one()
    assert fresh(db, j.id).status == "COMPLETED" and a.checksum_sha256 == hashlib.sha256(BYTES).hexdigest() and a.size_bytes == len(BYTES)
    assert a.quality == "1080p" and a.visibility == "private" and db.get(Movie, a.movie_id).status == "draft"
    assert len(list(Path(s.local_dir).iterdir())) == 1 and not (Path(s.tmp_dir) / str(j.id)).exists()
    assert process_one(c, p, s, dl, resolver=PUBLIC, probe_fn=INFO) is None  # queue empty


def test_summary_over_multiple_jobs(api, db, tmp_path):
    seed(db, 3); s, c, p, dl = rig(api, tmp_path)
    assert run_until_empty(c, p, s, dl, resolver=PUBLIC, probe_fn=INFO) == ["COMPLETED"] * 3
    assert db.query(MediaAsset).count() == 3


def test_failed_verification_does_not_complete_and_deletes_upload(api, db, tmp_path):
    (j,) = seed(db); s, c, p, dl = rig(api, tmp_path)
    p.verify = lambda ref, size: False
    assert process_one(c, p, s, dl, resolver=PUBLIC, probe_fn=INFO) == "VERIFY_FAILED"
    assert fresh(db, j.id).status == "RETRY_WAIT" and db.query(MediaAsset).count() == 0 and not list(Path(s.local_dir).iterdir())


def test_revoked_rights_block_attach_and_remove_stored_file(api, db, tmp_path):
    (j,) = seed(db); s, c, p, dl = rig(api, tmp_path)
    def probe_then_revoke(path):
        db.query(ContentRight).update({"review_status": "REVOKED"}); db.commit(); return INFO(path)
    assert process_one(c, p, s, dl, resolver=PUBLIC, probe_fn=probe_then_revoke) == "BLOCKED_RIGHTS"
    assert fresh(db, j.id).status == "BLOCKED_RIGHTS" and db.query(MediaAsset).count() == 0 and not list(Path(s.local_dir).iterdir())


def test_cancel_mid_run_stops_without_completing(api, db, tmp_path):
    (j,) = seed(db); s, c, p, dl = rig(api, tmp_path)
    def probe_then_cancel(path):
        db.query(ImportJob).update({"status": "CANCELLED", "lease_owner": None}); db.commit(); return INFO(path)
    assert process_one(c, p, s, dl, resolver=PUBLIC, probe_fn=probe_then_cancel) == "LEASE_LOST"
    assert fresh(db, j.id).status == "CANCELLED" and db.query(MediaAsset).count() == 0
    assert not (Path(s.tmp_dir) / str(j.id)).exists()


def test_crash_mid_upload_never_completes(api, db, tmp_path):
    (j,) = seed(db); s, c, p, dl = rig(api, tmp_path)
    def dying_upload(path, meta): raise KeyboardInterrupt  # simulates the Colab runtime dying
    p.upload = dying_upload
    try:
        process_one(c, p, s, dl, resolver=PUBLIC, probe_fn=INFO)
    except KeyboardInterrupt:
        pass
    assert fresh(db, j.id).status == "UPLOADING" and db.query(MediaAsset).count() == 0
    db.query(ImportJob).update({"lease_until": NOW - timedelta(seconds=1)}); db.commit()  # lease expires -> reclaimable
    assert process_one(c, LocalDirProvider(s.local_dir), s, dl, resolver=PUBLIC, probe_fn=INFO) == "COMPLETED"
    assert fresh(db, j.id).attempts == 2 and db.query(MediaAsset).count() == 1


def test_oversize_and_expired_sources_fail_without_retry(api, db, tmp_path):
    (j,) = seed(db); s, c, p, dl = rig(api, tmp_path)
    s.download_max_bytes = 100
    assert process_one(c, p, s, dl, resolver=PUBLIC, probe_fn=INFO) == "FILE_TOO_LARGE"
    assert fresh(db, j.id).status == "FAILED"
    (j2,) = seed(db); s, c, p, dl = rig(api, tmp_path, handler=lambda r: httpx.Response(404))
    assert process_one(c, p, s, dl, resolver=PUBLIC, probe_fn=INFO) == "SOURCE_EXPIRED"
    assert fresh(db, j2.id).status == "EXPIRED_SOURCE"


def test_unexpected_error_is_generic_and_retryable(api, db, tmp_path):
    (j,) = seed(db); s, c, p, dl = rig(api, tmp_path)
    def bad_probe(path): raise RuntimeError("secret https://media.example/0.mp4 token=abc")
    assert process_one(c, p, s, dl, resolver=PUBLIC, probe_fn=bad_probe) == "UNEXPECTED"
    jj = fresh(db, j.id)
    assert jj.status == "RETRY_WAIT" and "media.example" not in (jj.error_message_safe or "") and "token" not in (jj.error_message_safe or "")

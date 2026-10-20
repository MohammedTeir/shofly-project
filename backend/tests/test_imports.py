import uuid
from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy.exc import IntegrityError
from app.core.crypto import encrypt
from app.imports import ssrf
from app.imports.service import claim_next
from app.models import AuditLog, ContentRight, Episode, ImportJob, MediaAsset, Movie, Season, TvSeries, User
from tests.conftest import login

W = {"X-Worker-Token": "worker-secret-token"}
PUBLIC = lambda host, port, type=None: [(2, 1, 6, "", ("93.184.216.34", 443))]
NOW = datetime.now(timezone.utc)


@pytest.fixture(autouse=True)
def dns(monkeypatch):
    monkeypatch.setattr(ssrf, "RESOLVER", PUBLIC)


def H(tok): return {"Authorization": f"Bearer {tok}"}


def staff(client, db, tg_id=900, role="content_admin"):
    tok = login(client, {"id": tg_id, "language_code": "en"})["access_token"]
    db.query(User).filter(User.telegram_id == tg_id).update({"role": role}); db.commit()
    return H(tok)


def mk_right(db, kind, cid, status="APPROVED", days=30):
    r = ContentRight(content_kind=kind, content_id=cid, license_type="owned", proof_ref_encrypted=encrypt("doc-1"),
                     telegram_allowed=True, territories=["ALL"], valid_from=NOW - timedelta(days=1),
                     valid_until=NOW + timedelta(days=days), review_status=status)
    db.add(r); db.commit(); return r


def mk_job(db, status="READY", with_right=True, **kw):
    m = Movie(original_title="Owned Film", status="draft"); db.add(m); db.flush()
    u = db.query(User).first() or User(telegram_id=1, preferred_language="en")
    db.add(u); db.flush()
    j = ImportJob(source_type="direct_url", source_ref_encrypted=encrypt("https://media.example/a.mp4"), requested_by=u.id,
                  status=status, candidate_kind="movie", target_id=m.id, idempotency_key=uuid.uuid4().hex, **kw)
    db.add(j); db.commit()
    if with_right:
        mk_right(db, "movie", m.id)
    return j, m


def claim(client, who="worker-aaa"):
    r = client.post("/api/v1/worker/jobs/claim", json={"worker_id": who}, headers=W)
    assert r.status_code == 200, r.text
    return r.json()["job"]


def advance(client, jid, who="worker-aaa", to="VERIFYING"):
    for st in ("PROBING", "UPLOADING", "VERIFYING"):
        assert client.post(f"/api/v1/worker/jobs/{jid}/progress", json={"lease_owner": who, "status": st, "progress_percent": 50}, headers=W).status_code == 200
        if st == to: break


def done_body(who="worker-aaa", sha="a" * 64, **kw):
    return {"lease_owner": who, "verified": True, "provider": "local", "provider_ref": "secret/ref", "size_bytes": 10,
            "checksum_sha256": sha, "duration_sec": 60, "quality": "1080p", **kw}


# ---- SSRF ----
@pytest.mark.parametrize("url", ["http://media.example/x", "https://user:p@media.example/x", "https://media.example:8443/x",
                                 "https://evil.example/x", "ftp://media.example/x", "https:///x"])
def test_ssrf_rejects_bad_urls(url):
    with pytest.raises(ssrf.UnsafeURL):
        ssrf.validate_source_url(url, {"media.example"})


@pytest.mark.parametrize("ip", ["127.0.0.1", "10.0.0.5", "192.168.1.1", "169.254.169.254", "::1", "::ffff:127.0.0.1", "0.0.0.0", "fe80::1"])
def test_ssrf_rejects_private_resolution(ip):
    r = lambda h, p, type=None: [(2, 1, 6, "", (ip, 443))]
    with pytest.raises(ssrf.UnsafeURL):
        ssrf.validate_source_url("https://media.example/x", {"media.example"}, r)


def test_ssrf_accepts_public_and_empty_allowlist_rejects_all():
    assert ssrf.validate_source_url("https://media.example/x", {"media.example"}) == "media.example"
    with pytest.raises(ssrf.UnsafeURL):
        ssrf.validate_source_url("https://media.example/x", set())


# ---- admin API ----
def test_create_job_rbac_idempotency_and_no_secret_leak(client, db):
    member = H(login(client, {"id": 5, "language_code": "en"})["access_token"])
    body = {"source_type": "direct_url", "source_ref": "https://media.example/a.mp4", "idempotency_key": "key-12345678"}
    assert client.post("/api/v1/admin/import-jobs", json=body, headers=member).status_code == 403
    a = staff(client, db)
    r = client.post("/api/v1/admin/import-jobs", json=body, headers=a)
    assert r.status_code == 201 and r.json()["status"] == "NEEDS_REVIEW" and "a.mp4" not in r.text
    assert client.post("/api/v1/admin/import-jobs", json=body, headers=a).json()["id"] == r.json()["id"]
    assert db.query(ImportJob).count() == 1
    assert client.post("/api/v1/admin/import-jobs", json={**body, "source_ref": "https://media.example/b.mp4"}, headers=a).status_code == 409
    assert "a.mp4" not in client.get(f"/api/v1/admin/import-jobs/{r.json()['id']}", headers=a).text
    bad = {**body, "idempotency_key": "key-87654321"}
    assert client.post("/api/v1/admin/import-jobs", json={**bad, "source_ref": "https://evil.example/x.mp4"}, headers=a).json()["error"]["code"] == "UNSAFE_SOURCE"
    assert client.post("/api/v1/admin/import-jobs", json={**bad, "source_type": "google_drive"}, headers=a).status_code == 422


def test_approve_needs_approved_rights_and_only_rights_admin_approves(client, db):
    a = staff(client, db)
    jid = client.post("/api/v1/admin/import-jobs", json={"source_type": "direct_url", "source_ref": "https://media.example/a.mp4",
                                                          "idempotency_key": "key-aaaaaaaa"}, headers=a).json()["id"]
    m = Movie(original_title="M"); db.add(m); db.commit()
    ap = {"candidate_kind": "movie", "target_id": str(m.id)}
    assert client.post(f"/api/v1/admin/import-jobs/{jid}/approve", json=ap, headers=a).json()["error"]["code"] == "RIGHTS_NOT_APPROVED"
    right = {"content_kind": "movie", "content_id": str(m.id), "license_type": "owned", "proof_ref": "contract-77", "telegram_allowed": True,
             "territories": ["ALL"], "valid_from": (NOW - timedelta(days=1)).isoformat(), "valid_until": (NOW + timedelta(days=9)).isoformat()}
    rid = client.post("/api/v1/admin/rights", json=right, headers=a).json()["id"]
    assert client.post(f"/api/v1/admin/rights/{rid}/approve", headers=a).status_code == 403  # content admin can't self-approve
    assert client.post(f"/api/v1/admin/import-jobs/{jid}/approve", json=ap, headers=a).status_code == 409  # still PENDING
    ra = staff(client, db, 901, "rights_admin")
    assert client.post(f"/api/v1/admin/rights/{rid}/approve", headers=ra).json()["review_status"] == "APPROVED"
    assert client.post(f"/api/v1/admin/import-jobs/{jid}/approve", json=ap, headers=a).json()["status"] == "READY"
    bad = {**right, "valid_until": right["valid_from"]}
    assert client.post("/api/v1/admin/rights", json=bad, headers=a).status_code == 422
    assert {x.action for x in db.query(AuditLog)} >= {"import.create", "rights.create", "rights.approved", "import.approve"}
    client.post(f"/api/v1/admin/rights/{rid}/revoke", headers=ra)
    assert db.query(ContentRight).one().review_status == "REVOKED"


def test_cancel_and_invalid_transitions(client, db):
    a = staff(client, db); j, _ = mk_job(db, "READY")
    assert client.post(f"/api/v1/admin/import-jobs/{j.id}/cancel", headers=a).json()["status"] == "CANCELLED"
    assert client.post(f"/api/v1/admin/import-jobs/{j.id}/cancel", headers=a).status_code == 409
    assert claim(client) is None  # cancelled jobs are never claimed


# ---- worker API ----
def test_worker_requires_token(client):
    assert client.post("/api/v1/worker/jobs/claim", json={"worker_id": "abc"}).status_code == 401
    assert client.post("/api/v1/worker/jobs/claim", json={"worker_id": "abc"}, headers={"X-Worker-Token": "x"}).status_code == 401
    assert client.get("/api/v1/worker/ping", headers=W).status_code == 200
    assert client.get("/api/v1/admin/import-jobs", headers=W).status_code in (401, 403)  # worker token grants no admin power


def test_claim_is_exclusive_and_cas_blocks_stale_claim(client, db):
    j, _ = mk_job(db)
    first = claim(client, "worker-aaa")
    assert first["id"] == str(j.id) and first["source_ref"] == "https://media.example/a.mp4" and first["attempts"] == 1
    assert claim(client, "worker-bbb") is None
    db.expire_all(); jj = db.get(ImportJob, j.id)
    assert jj.lease_owner == "worker-aaa" and jj.status == "DOWNLOADING"
    # stale-read race: a second claimer that read epoch 0 must lose the compare-and-set
    from sqlalchemy import update
    res = db.execute(update(ImportJob).where(ImportJob.id == j.id, ImportJob.lease_epoch == 0).values(lease_owner="worker-bbb")); db.commit()
    assert res.rowcount == 0


def test_expired_lease_is_reclaimed_and_old_owner_is_rejected(client, db):
    j, _ = mk_job(db); claim(client, "worker-aaa")
    db.query(ImportJob).update({"lease_until": NOW - timedelta(seconds=5)}); db.commit()
    second = claim(client, "worker-bbb")
    assert second and second["attempts"] == 2
    for path, body in (("heartbeat", {}), ("complete", done_body("worker-aaa"))):
        r = client.post(f"/api/v1/worker/jobs/{j.id}/{path}", json={"lease_owner": "worker-aaa", **body}, headers=W)
        assert r.status_code == 409 and r.json()["error"]["code"] == "LEASE_LOST"


def test_lease_expiry_exhausts_attempts(client, db):
    j, _ = mk_job(db, attempts=3, status="DOWNLOADING", lease_owner="w-old", lease_until=NOW - timedelta(seconds=1))
    assert claim(client) is None
    db.expire_all(); assert db.get(ImportJob, j.id).status == "FAILED"


def test_complete_creates_one_verified_private_asset_and_dedups(client, db):
    j, m = mk_job(db); claim(client); advance(client, j.id)
    r = client.post(f"/api/v1/worker/jobs/{j.id}/complete", json=done_body(), headers=W)
    assert r.status_code == 200 and r.json()["duplicate"] is False
    a = db.query(MediaAsset).one()
    assert a.movie_id == m.id and a.visibility == "private" and a.upload_status == "verified" and "secret/ref" not in a.provider_ref_encrypted
    db.expire_all(); assert db.get(ImportJob, j.id).status == "COMPLETED" and db.get(Movie, m.id).status == "draft"  # not auto-published
    # same bytes uploaded again for the same target -> no second asset
    j2 = ImportJob(source_type="direct_url", source_ref_encrypted=encrypt("https://media.example/a2.mp4"), requested_by=j.requested_by,
                   status="READY", candidate_kind="movie", target_id=m.id, idempotency_key=uuid.uuid4().hex); db.add(j2); db.commit()
    claim(client, "worker-ccc"); advance(client, j2.id, "worker-ccc")
    assert client.post(f"/api/v1/worker/jobs/{j2.id}/complete", json=done_body("worker-ccc"), headers=W).json()["duplicate"] is True
    assert db.query(MediaAsset).count() == 1


def test_complete_guards(client, db):
    j, _ = mk_job(db); claim(client)
    assert client.post(f"/api/v1/worker/jobs/{j.id}/complete", json=done_body(), headers=W).json()["error"]["code"] == "INVALID_STATE"  # still DOWNLOADING
    advance(client, j.id)
    assert client.post(f"/api/v1/worker/jobs/{j.id}/complete", json=done_body(verified=False), headers=W).json()["error"]["code"] == "NOT_VERIFIED"
    assert client.post(f"/api/v1/worker/jobs/{j.id}/complete", json=done_body(sha="xyz"), headers=W).status_code == 422
    assert db.query(MediaAsset).count() == 0


def test_revoked_or_expired_rights_block_completion(client, db):
    j, m = mk_job(db); claim(client); advance(client, j.id)
    db.query(ContentRight).update({"valid_until": NOW - timedelta(minutes=1)}); db.commit()
    r = client.post(f"/api/v1/worker/jobs/{j.id}/complete", json=done_body(), headers=W)
    assert r.status_code == 409 and r.json()["error"]["code"] == "BLOCKED_RIGHTS"
    db.expire_all(); assert db.get(ImportJob, j.id).status == "BLOCKED_RIGHTS" and db.query(MediaAsset).count() == 0


def test_fail_retry_backoff_exhaustion_and_expired_source(client, db):
    j, _ = mk_job(db); claim(client)
    f = lambda **k: client.post(f"/api/v1/worker/jobs/{j.id}/fail", json={"lease_owner": "worker-aaa", "error_code": "NET_ERROR", **k}, headers=W)
    assert f().json()["status"] == "RETRY_WAIT"
    assert claim(client) is None  # backoff not elapsed
    db.query(ImportJob).update({"next_attempt_at": NOW - timedelta(seconds=1)}); db.commit()
    assert claim(client)["attempts"] == 2
    assert f(retryable=False).json()["status"] == "FAILED"
    a = staff(client, db)
    assert client.post(f"/api/v1/admin/import-jobs/{j.id}/retry", headers=a).json()["status"] == "READY"
    claim(client); r = client.post(f"/api/v1/worker/jobs/{j.id}/fail", json={"lease_owner": "worker-aaa", "error_code": "SOURCE_EXPIRED"}, headers=W)
    assert r.json()["status"] == "EXPIRED_SOURCE"


def test_cancel_while_running_stops_worker(client, db):
    j, _ = mk_job(db); claim(client)
    staff_h = staff(client, db); client.post(f"/api/v1/admin/import-jobs/{j.id}/cancel", headers=staff_h)
    r = client.post(f"/api/v1/worker/jobs/{j.id}/heartbeat", json={"lease_owner": "worker-aaa"}, headers=W)
    assert r.status_code == 409 and r.json()["error"]["code"] == "JOB_CANCELLED"


def test_asset_requires_exactly_one_target(db):
    m = Movie(original_title="x"); s = TvSeries(original_title="s"); db.add_all([m, s]); db.flush()
    se = Season(series_id=s.id, season_number=1); db.add(se); db.flush()
    e = Episode(season_id=se.id, episode_number=1); db.add(e); db.flush()
    db.add(MediaAsset(movie_id=m.id, episode_id=e.id, provider="local", provider_ref_encrypted="x", size_bytes=1, checksum_sha256="b" * 64))
    with pytest.raises(IntegrityError):
        db.commit()


def test_ready_endpoint(client):
    assert client.get("/health/ready").json() == {"status": "ready"}


def test_concurrent_claims_have_exactly_one_winner_on_postgres(db):
    import os
    from concurrent.futures import ThreadPoolExecutor
    from app.core.db import SessionLocal
    if not os.environ.get("DATABASE_URL", "").startswith("postgresql"):
        pytest.skip("needs PostgreSQL (SKIP LOCKED + row locking)")
    j, _ = mk_job(db)

    def attempt(i):
        with SessionLocal() as s:
            got = claim_next(s, f"worker-{i:03d}")
            return got.lease_owner if got else None
    with ThreadPoolExecutor(8) as ex:
        results = list(ex.map(attempt, range(8)))
    assert len([r for r in results if r]) == 1
    db.expire_all(); assert db.get(ImportJob, j.id).attempts == 1

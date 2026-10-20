from datetime import datetime, timedelta, timezone
import uuid
import pytest
from app.core.crypto import encrypt
from app.models import AuditLog, ContentRight, Episode, MediaAsset, Movie, Season, TvSeries, User
from tests.conftest import login

NOW = datetime.now(timezone.utc)
M = {"id": 321, "language_code": "en"}


def H(t): return {"Authorization": f"Bearer {t}"}


def who(client, db, tg, role):
    tok = login(client, {"id": tg, "language_code": "en"})["access_token"]
    db.query(User).filter(User.telegram_id == tg).update({"role": role}); db.commit(); return H(tok)


def add_asset(db, **key):
    db.add(MediaAsset(provider="local", provider_ref_encrypted="x", size_bytes=5, checksum_sha256="c" * 64, upload_status="verified", **key)); db.commit()


def add_right(db, kind, cid, status="APPROVED", until=30):
    r = ContentRight(content_kind=kind, content_id=cid, license_type="owned", proof_ref_encrypted=encrypt("p"), telegram_allowed=True,
                     territories=["ALL"], valid_from=NOW - timedelta(days=1), valid_until=NOW + timedelta(days=until), review_status=status)
    db.add(r); db.commit(); return r


def test_movie_publish_requires_metadata_asset_and_rights_then_hides_on_expiry_and_unpublish(client, db):
    a = who(client, db, 900, "content_admin"); member = H(login(client, M)["access_token"])
    m = Movie(original_title="Owned"); db.add(m); db.commit()
    pub = lambda: client.post(f"/api/v1/admin/catalog/movie/{m.id}/publish", headers=a)
    assert pub().json()["error"]["details"]["blockers"] == ["METADATA_NOT_VERIFIED", "NO_VERIFIED_ASSET", "RIGHTS_NOT_VALID"]
    client.post(f"/api/v1/admin/catalog/movie/{m.id}/verify-metadata", headers=a)
    add_asset(db, movie_id=m.id)
    assert pub().json()["error"]["details"]["blockers"] == ["RIGHTS_NOT_VALID"]
    right = add_right(db, "movie", m.id, status="PENDING")
    assert pub().status_code == 409  # pending rights do not count
    right.review_status = "APPROVED"; db.commit()
    assert pub().json() == {"status": "published"}
    assert [i["id"] for i in client.get("/api/v1/catalog/movies", headers=member).json()["items"]] == [str(m.id)]
    right.valid_until = NOW - timedelta(minutes=1); db.commit()  # license expires: gone immediately, no admin action
    assert client.get("/api/v1/catalog/movies", headers=member).json()["items"] == []
    assert client.get(f"/api/v1/movies/{m.id}", headers=member).status_code == 404
    right.valid_until = NOW + timedelta(days=5); db.commit()
    assert client.get(f"/api/v1/movies/{m.id}", headers=member).status_code == 200
    client.post(f"/api/v1/admin/catalog/movie/{m.id}/unpublish", headers=a)
    assert client.get(f"/api/v1/movies/{m.id}", headers=member).status_code == 404
    assert {x.action for x in db.query(AuditLog)} >= {"metadata.verify", "catalog.publish", "catalog.unpublish"}


def test_series_flow_seasons_episodes_and_deliverable_rule(client, db):
    a = who(client, db, 900, "content_admin"); member = H(login(client, M)["access_token"])
    sid = client.post("/api/v1/admin/catalog/series", json={"original_title": "Owned Series"}, headers=a).json()["id"]
    seid = client.post(f"/api/v1/admin/catalog/series/{sid}/seasons", json={"season_number": 1}, headers=a).json()["id"]
    assert client.post(f"/api/v1/admin/catalog/series/{sid}/seasons", json={"season_number": 1}, headers=a).status_code == 409
    e1 = client.post(f"/api/v1/admin/catalog/seasons/{seid}/episodes", json={"episode_number": 1, "title": "Pilot"}, headers=a).json()["id"]
    client.post(f"/api/v1/admin/catalog/series/{sid}/verify-metadata", headers=a)
    assert client.post(f"/api/v1/admin/catalog/series/{sid}/publish", headers=a).json()["error"]["details"]["blockers"] == ["NO_DELIVERABLE_EPISODE"]
    add_asset(db, episode_id=uuid.UUID(e1)); add_right(db, "episode", uuid.UUID(e1))
    d = client.get(f"/api/v1/admin/catalog/series/{sid}", headers=a).json()
    assert d["blockers"] == [] and d["episodes"][0]["deliverable"] is True and len(d["assets"]) == 1 and len(d["rights"]) == 1
    assert client.post(f"/api/v1/admin/catalog/series/{sid}/publish", headers=a).status_code == 200
    assert len(client.get("/api/v1/catalog/series", headers=member).json()["items"]) == 1


def test_member_cannot_publish_and_overview_counts(client, db):
    member = H(login(client, M)["access_token"]); m = Movie(original_title="x"); db.add(m); db.commit()
    assert client.post(f"/api/v1/admin/catalog/movie/{m.id}/publish", headers=member).status_code == 403
    assert client.get("/api/v1/admin/overview", headers=member).status_code == 403
    a = who(client, db, 900, "content_admin")
    add_right(db, "movie", m.id, until=5)
    o = client.get("/api/v1/admin/overview", headers=a).json()
    assert o["movies"] == {"total": 1, "published": 0, "draft": 1} and o["rights_expiring_14d"] == 1 and o["users"] == 2
    lst = client.get("/api/v1/admin/catalog/movie?status=draft&q=x", headers=a).json()["items"]
    assert len(lst) == 1 and lst[0]["metadata_verified"] is False


def test_rights_list_hides_proof_and_filters(client, db):
    ra = who(client, db, 901, "rights_admin"); m = Movie(original_title="Label Me"); db.add(m); db.commit()
    add_right(db, "movie", m.id, status="PENDING")
    r = client.get("/api/v1/admin/rights?status=PENDING", headers=ra)
    assert r.json()["items"][0]["label"] == "Label Me" and "proof" not in r.text
    assert client.get("/api/v1/admin/rights?status=APPROVED", headers=ra).json()["items"] == []


def test_user_management_super_admin_only_with_audit(client, db):
    sa = who(client, db, 902, "super_admin"); ca = who(client, db, 900, "content_admin")
    target = db.query(User).filter(User.telegram_id == 900).one()
    assert client.get("/api/v1/admin/users", headers=ca).status_code == 403
    assert client.get("/api/v1/admin/users", headers=sa).status_code == 200
    me = db.query(User).filter(User.telegram_id == 902).one()
    assert client.patch(f"/api/v1/admin/users/{me.id}", json={"role": "member"}, headers=sa).status_code == 409
    assert client.patch(f"/api/v1/admin/users/{target.id}", json={"role": "root"}, headers=sa).status_code == 422
    r = client.patch(f"/api/v1/admin/users/{target.id}", json={"role": "moderator", "status": "suspended"}, headers=sa)
    assert r.json()["role"] == "moderator"
    assert client.get("/api/v1/me", headers=ca).status_code == 401  # suspended users are locked out immediately
    assert db.query(AuditLog).filter_by(action="user.update").count() == 1

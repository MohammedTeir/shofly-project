import uuid
from datetime import datetime, timedelta, timezone
import pytest
from app.core.crypto import encrypt
from app.models import AuditLog, ContentRight, Episode, MediaAsset, Movie, Season, TvSeries, User
from tests.conftest import login

NOW = datetime.now(timezone.utc)
B = {"X-Bot-Token": "bot-secret-token"}
TG = {"id": 77, "language_code": "en"}


def H(t): return {"Authorization": f"Bearer {t}"}


def setup(db, *, provider="telegram", **right):
    m = Movie(original_title="Owned", status="published", metadata_verified=True); db.add(m); db.flush()
    a = MediaAsset(movie_id=m.id, provider=provider, provider_ref_encrypted=encrypt("-1001234:55:SECRETFILEID"), size_bytes=2048,
                   checksum_sha256=uuid.uuid4().hex * 2, quality="1080p", upload_status="verified"); db.add(a)
    kw = dict(content_kind="movie", content_id=m.id, license_type="owned", proof_ref_encrypted="x", telegram_allowed=True, territories=["ALL"],
              valid_from=NOW - timedelta(days=1), valid_until=NOW + timedelta(days=5), review_status="APPROVED"); kw.update(right)
    db.add(ContentRight(**kw)); db.commit()
    return m, a


def tok(client): return H(login(client, TG)["access_token"])


def test_access_returns_opaque_deep_link_without_storage_details(client, db):
    m, a = setup(db)
    r = client.post(f"/api/v1/media/{a.id}/access", headers=tok(client))
    assert r.status_code == 200 and r.json() == {"delivery_type": "telegram_bot", "bot_deep_link": f"https://t.me/ShoflyBot?start=dl_{a.id.hex}"}
    assert "SECRETFILEID" not in r.text and "1001234" not in r.text


@pytest.mark.parametrize("right,code,status", [
    ({"review_status": "PENDING"}, "RIGHTS_NOT_AVAILABLE", 403),
    ({"review_status": "REVOKED"}, "RIGHTS_NOT_AVAILABLE", 403),
    ({"valid_until": NOW - timedelta(minutes=1)}, "RIGHTS_NOT_AVAILABLE", 403),
    ({"valid_from": NOW + timedelta(days=1)}, "RIGHTS_NOT_AVAILABLE", 403),
    ({"telegram_allowed": False, "web_allowed": True}, "RIGHTS_NOT_AVAILABLE", 403),   # right exists but not for this platform
    ({"territories": ["US"]}, "TERRITORY_RESTRICTED", 403),                              # unknown viewer territory is never guessed
])
def test_denials_by_rights(client, db, right, code, status):
    m, a = setup(db, **right)
    for path in (f"/api/v1/media/{a.id}/access", f"/api/v1/media/{a.id}/telegram-delivery"):
        r = client.post(path, headers={**tok(client), **B})
        assert r.status_code == status and r.json()["error"]["code"] == code


def test_unpublished_unverified_unsupported_and_unauthenticated(client, db):
    m, a = setup(db); h = tok(client)
    m.status = "draft"; db.commit()
    assert client.post(f"/api/v1/media/{a.id}/access", headers=h).status_code == 404  # looks identical to "does not exist"
    m.status = "published"; a.upload_status = "uploading"; db.commit()
    assert client.post(f"/api/v1/media/{a.id}/access", headers=h).status_code == 404
    a.upload_status = "verified"; a.provider = "local"; db.commit()
    assert client.post(f"/api/v1/media/{a.id}/access", headers=h).json()["error"]["code"] == "MEDIA_DELIVERY_UNSUPPORTED"
    assert client.post(f"/api/v1/media/{a.id}/access").status_code == 401
    assert client.post(f"/api/v1/media/{uuid.uuid4()}/access", headers=h).status_code == 404


def test_suspended_user_is_denied_immediately(client, db):
    m, a = setup(db); h = tok(client)
    db.query(User).update({"status": "suspended"}); db.commit()
    assert client.post(f"/api/v1/media/{a.id}/access", headers=h).status_code == 401


def test_territory_all_plus_specific_allows(client, db):
    m, a = setup(db, territories=["US", "ALL"])
    assert client.post(f"/api/v1/media/{a.id}/access", headers=tok(client)).status_code == 200


def test_bot_delivery_needs_both_secrets_returns_ref_and_audits(client, db):
    m, a = setup(db); h = tok(client)
    assert client.post(f"/api/v1/media/{a.id}/telegram-delivery", headers=h).status_code == 401           # user alone is not enough
    assert client.post(f"/api/v1/media/{a.id}/telegram-delivery", headers={"X-Bot-Token": "nope", **h}).status_code == 401
    assert client.post(f"/api/v1/media/{a.id}/telegram-delivery", headers=B).status_code == 401           # bot alone is not enough
    r = client.post(f"/api/v1/media/{a.id}/telegram-delivery", headers={**h, **B})
    assert r.status_code == 200 and r.json() == {"chat_id": -1001234, "message_id": 55} and "SECRETFILEID" not in r.text
    log = db.query(AuditLog).filter_by(action="media.deliver").one()
    assert str(log.entity_id) == str(a.id) and log.actor_id is not None


def test_titles_list_only_deliverable_assets(client, db):
    m, a = setup(db); h = tok(client)
    d = client.get(f"/api/v1/movies/{m.id}", headers=h).json()
    assert [x["id"] for x in d["assets"]] == [str(a.id)] and d["assets"][0]["quality"] == "1080p" and "provider" not in d["assets"][0]
    db.query(ContentRight).update({"telegram_allowed": False, "web_allowed": True}); db.commit()
    assert client.get(f"/api/v1/movies/{m.id}", headers=h).json()["assets"] == []


def test_episode_assets_in_season_listing(client, db):
    s = TvSeries(original_title="S", status="published", metadata_verified=True); db.add(s); db.flush()
    se = Season(series_id=s.id, season_number=1); db.add(se); db.flush()
    e1, e2 = Episode(season_id=se.id, episode_number=1), Episode(season_id=se.id, episode_number=2); db.add_all([e1, e2]); db.flush()
    db.add(MediaAsset(episode_id=e1.id, provider="telegram", provider_ref_encrypted=encrypt("-1:2:F"), size_bytes=5, checksum_sha256="d" * 64, upload_status="verified"))
    db.add(ContentRight(content_kind="episode", content_id=e1.id, license_type="o", proof_ref_encrypted="x", telegram_allowed=True, territories=["ALL"],
                        valid_from=NOW - timedelta(days=1), valid_until=NOW + timedelta(days=5), review_status="APPROVED")); db.commit()
    eps = client.get(f"/api/v1/catalog/series/{s.id}/seasons/1", headers=tok(client)).json()["episodes"]
    assert len(eps[0]["assets"]) == 1 and eps[1]["assets"] == []

import time
from app.fixtures import make_visible
from tests.conftest import login, make_init_data
from app.models import LocalizedMetadata, Movie, User

U = {"id": 111, "first_name": "Sam", "language_code": "en"}


def H(tok): return {"Authorization": f"Bearer {tok}"}


def test_first_login_creates_one_user_and_relogin_resolves_same(client, db):
    a, b = login(client, U), login(client, U)
    assert a["user"]["id"] == b["user"]["id"]
    assert db.query(User).count() == 1


def test_forged_and_expired_init_data_rejected(client):
    r = client.post("/api/v1/auth/telegram", json={"init_data": make_init_data(U, tamper=True)})
    assert r.status_code == 401 and r.json()["error"]["code"] == "INVALID_INIT_DATA"
    r = client.post("/api/v1/auth/telegram", json={"init_data": make_init_data(U, token="999:OTHER")})
    assert r.status_code == 401
    r = client.post("/api/v1/auth/telegram", json={"init_data": make_init_data(U, auth_date=int(time.time()) - 10**6)})
    assert r.status_code == 401 and r.json()["error"]["code"] == "INIT_DATA_EXPIRED"


def test_language_seeded_from_telegram_then_default_ar(client):
    assert login(client, U)["user"]["preferred_language"] == "en"
    assert login(client, {"id": 222, "language_code": "fr"})["user"]["preferred_language"] == "ar"


def test_explicit_choice_persists_and_beats_telegram_locale(client):
    tok = login(client, U)["access_token"]
    r = client.patch("/api/v1/me/preferences", json={"preferred_language": "ar"}, headers=H(tok))
    assert r.status_code == 200 and r.json()["language_source"] == "user"
    again = login(client, {**U, "language_code": "en"})  # "another device", Telegram says en
    assert again["user"]["preferred_language"] == "ar"
    assert client.get("/api/v1/me", headers=H(again["access_token"])).json()["preferred_language"] == "ar"


def test_unsupported_language_is_422_and_not_saved(client):
    tok = login(client, U)["access_token"]
    r = client.patch("/api/v1/me/preferences", json={"preferred_language": "xx"}, headers=H(tok))
    assert r.status_code == 422
    assert client.get("/api/v1/me", headers=H(tok)).json()["preferred_language"] == "en"


def test_auth_required(client):
    assert client.get("/api/v1/me").status_code == 401
    assert client.get("/api/v1/catalog/movies", headers=H("junk")).status_code == 401


def test_catalog_localization_fallback_and_publish_filter(client, db):
    m1 = Movie(original_title="Interstellar", status="published")
    m2 = Movie(original_title="Draft Film", status="draft")
    db.add_all([m1, m2]); db.commit()
    make_visible(db, m1)
    db.add(LocalizedMetadata(content_kind="movie", content_id=m1.id, language_code="en", title="Interstellar EN"))
    db.commit()
    tok = login(client, U)["access_token"]  # en
    items = client.get("/api/v1/catalog/movies", headers=H(tok)).json()["items"]
    assert [i["title"] for i in items] == ["Interstellar EN"]
    client.patch("/api/v1/me/preferences", json={"preferred_language": "ar"}, headers=H(tok))
    i = client.get("/api/v1/catalog/movies", headers=H(tok)).json()["items"][0]
    assert i["title"] == "Interstellar" and i["title_language"] == "original"
    assert len(client.get("/api/v1/catalog/search?q=Interstellar", headers=H(tok)).json()["items"]) == 1

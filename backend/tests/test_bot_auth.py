from app.models import Movie, User
from app.fixtures import make_visible
from tests.conftest import login

B = {"X-Bot-Token": "bot-secret-token"}
TG = {"id": 5, "first_name": "Bo", "language_code": "en"}


def test_bot_auth_creates_same_user_as_miniapp_and_checks_secret(client, db):
    r = client.post("/api/v1/bot/auth", json=TG, headers=B)
    assert r.status_code == 200 and r.json()["user"]["preferred_language"] == "en"
    assert login(client, TG)["user"]["id"] == r.json()["user"]["id"]  # same account across surfaces
    assert db.query(User).count() == 1
    assert client.post("/api/v1/bot/auth", json=TG).status_code == 401
    assert client.post("/api/v1/bot/auth", json=TG, headers={"X-Bot-Token": "nope"}).status_code == 401
    assert client.post("/api/v1/bot/auth", json={**TG, "is_bot": True}, headers=B).status_code == 400


def test_detail_reports_favorited(client, db):
    m = Movie(original_title="F", status="published"); db.add(m); db.commit(); make_visible(db, m)
    tok = {"Authorization": "Bearer " + login(client, TG)["access_token"]}
    assert client.get(f"/api/v1/movies/{m.id}", headers=tok).json()["favorited"] is False
    client.put(f"/api/v1/me/favorites/movie/{m.id}", headers=tok)
    assert client.get(f"/api/v1/movies/{m.id}", headers=tok).json()["favorited"] is True

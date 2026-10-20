from pathlib import Path
from sqlalchemy import create_engine, inspect
from alembic import command
from alembic.config import Config
from app.core.ratelimit import limiter
from app.models import AuditLog, Episode, Movie, MovieCollection, CollectionMovie, Season, TvSeries, User
from app.fixtures import make_visible
from tests.conftest import login

U = {"id": 111, "first_name": "Sam", "language_code": "en"}
V = {"id": 222, "first_name": "Eve", "language_code": "en"}


def H(tok): return {"Authorization": f"Bearer {tok}"}


def admin_token(client, db, tg=None, role="super_admin"):
    tok = login(client, tg or {"id": 999, "language_code": "en"})["access_token"]
    db.query(User).filter(User.telegram_id == (tg or {"id": 999})["id"]).update({"role": role}); db.commit()
    return tok


def test_member_cannot_use_admin_and_admin_creates_draft_with_audit(client, db):
    member = login(client, U)["access_token"]
    assert client.post("/api/v1/admin/catalog/movies", json={"original_title": "X"}, headers=H(member)).status_code == 403
    tok = admin_token(client, db)
    r = client.post("/api/v1/admin/catalog/movies", json={"original_title": "Drafty", "tmdb_id": 5}, headers=H(tok))
    assert r.status_code == 201 and r.json()["status"] == "draft"
    assert client.post("/api/v1/admin/catalog/movies", json={"original_title": "Dup", "tmdb_id": 5}, headers=H(tok)).status_code == 409
    mid = r.json()["id"]
    assert client.get(f"/api/v1/movies/{mid}", headers=H(member)).status_code == 404  # drafts invisible
    assert db.query(AuditLog).filter_by(action="movie.create").count() == 1
    logs = client.get("/api/v1/admin/audit-logs", headers=H(tok)).json()["items"]
    assert logs and logs[0]["action"] == "movie.create"


def test_translation_upsert_and_unsupported_lang(client, db):
    tok = admin_token(client, db)
    mid = client.post("/api/v1/admin/catalog/movies", json={"original_title": "Orig"}, headers=H(tok)).json()["id"]
    assert client.put(f"/api/v1/admin/catalog/movie/{mid}/translations/fr", json={"title": "x"}, headers=H(tok)).status_code == 422
    assert client.put(f"/api/v1/admin/catalog/movie/{mid}/translations/ar", json={"title": "أصلي"}, headers=H(tok)).status_code == 200
    assert client.put(f"/api/v1/admin/catalog/movie/{mid}/translations/ar", json={"title": "أصلي 2"}, headers=H(tok)).status_code == 200


def test_collection_ordered_and_hides_unpublished(client, db):
    ms = [Movie(original_title=t, status=s) for t, s in (("A", "published"), ("B", "draft"), ("C", "published"))]
    db.add_all(ms); db.commit(); make_visible(db, ms[0], ms[2])
    tok = admin_token(client, db)
    r = client.post("/api/v1/admin/catalog/collections", json={"name": "Saga", "movie_ids": [str(ms[2].id), str(ms[1].id), str(ms[0].id)]}, headers=H(tok))
    assert r.status_code == 201
    items = client.get(f"/api/v1/collections/{r.json()['id']}", headers=H(tok)).json()["items"]
    assert [i["title"] for i in items] == ["C", "A"]


def test_favorites_idempotent_and_per_user(client, db):
    m = Movie(original_title="Fav", status="published"); db.add(m); db.commit(); make_visible(db, m)
    a, b = login(client, U)["access_token"], login(client, V)["access_token"]
    for _ in range(3):
        assert client.put(f"/api/v1/me/favorites/movie/{m.id}", headers=H(a)).status_code == 200
    assert len(client.get("/api/v1/me/favorites", headers=H(a)).json()["items"]) == 1
    assert client.get("/api/v1/me/favorites", headers=H(b)).json()["items"] == []
    assert client.put(f"/api/v1/me/favorites/book/{m.id}", headers=H(a)).status_code == 422
    client.delete(f"/api/v1/me/favorites/movie/{m.id}", headers=H(a))
    assert client.get("/api/v1/me/favorites", headers=H(a)).json()["items"] == []


def test_series_detail_and_season_episodes_ordered(client, db):
    s = TvSeries(original_title="Ser", status="published"); db.add(s); db.flush()
    se = Season(series_id=s.id, season_number=0); se2 = Season(series_id=s.id, season_number=1); db.add_all([se, se2]); db.flush()
    db.add_all([Episode(season_id=se2.id, episode_number=n) for n in (3, 1, 2)]); db.commit(); make_visible(db, s)
    tok = login(client, U)["access_token"]
    d = client.get(f"/api/v1/series/{s.id}", headers=H(tok)).json()
    assert [x["season_number"] for x in d["seasons"]] == [0, 1]  # specials first
    eps = client.get(f"/api/v1/catalog/series/{s.id}/seasons/1", headers=H(tok)).json()["episodes"]
    assert [e["episode_number"] for e in eps] == [1, 2, 3]


def test_pagination_cursor(client, db):
    ms = [Movie(original_title=f"M{i}", status="published") for i in range(5)]; db.add_all(ms); db.commit(); make_visible(db, *ms)
    tok = login(client, U)["access_token"]
    p1 = client.get("/api/v1/catalog/movies?limit=2", headers=H(tok)).json()
    p2 = client.get(f"/api/v1/catalog/movies?limit=2&cursor={p1['next_cursor']}", headers=H(tok)).json()
    ids = [i["id"] for i in p1["items"] + p2["items"]]
    assert len(ids) == len(set(ids)) == 4 and p2["next_cursor"] == "4"


def test_auth_rate_limit(client):
    limiter.reset()
    codes = [client.post("/api/v1/auth/telegram", json={"init_data": "a=b"}).status_code for _ in range(22)]
    assert codes[:20] == [401] * 20 and codes[20] == 429
    limiter.reset()


def test_alembic_upgrade_downgrade(tmp_path):
    cfg = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    cfg.set_main_option("script_location", str(Path(__file__).parents[1] / "migrations"))
    url = f"sqlite:///{tmp_path}/m.db"
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    tables = set(inspect(create_engine(url)).get_table_names())
    assert {"users", "movies", "favorites", "collection_movies", "audit_logs", "localized_metadata", "import_jobs", "media_assets", "content_rights"} <= tables
    command.downgrade(cfg, "base")
    assert set(inspect(create_engine(url)).get_table_names()) <= {"alembic_version"}

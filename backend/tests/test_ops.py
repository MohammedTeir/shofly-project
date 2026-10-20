import json
from pathlib import Path
from app.models import AuditLog, User
from scripts.make_admin import set_role
from tests.conftest import login


def test_request_id_is_echoed_sanitized_and_matches_error_body(client):
    r = client.get("/api/v1/me", headers={"X-Request-ID": "abc-123"})
    assert r.headers["x-request-id"] == "abc-123" and r.json()["error"]["request_id"] == "abc-123"
    r = client.get("/api/v1/me", headers={"X-Request-ID": "bad id\twith spaces"})
    assert r.headers["x-request-id"].startswith("req_") and r.json()["error"]["request_id"] == r.headers["x-request-id"]


def test_bootstrap_admin_creates_or_updates_and_audits(db, client):
    u = set_role(db, 4242, "super_admin")  # person has never opened the bot
    assert u.role == "super_admin" and db.query(User).count() == 1
    tok = login(client, {"id": 4242, "language_code": "en"})
    assert tok["user"]["role"] == "super_admin" and db.query(User).count() == 1  # same row after first login
    set_role(db, 4242, "member")
    assert db.query(User).one().role == "member" and db.query(AuditLog).filter_by(action="user.bootstrap_role").count() == 2
    import pytest
    with pytest.raises(ValueError):
        set_role(db, 4242, "root")


def test_openapi_snapshot_matches(client):
    snap = Path(__file__).resolve().parents[1] / "openapi.snapshot.json"
    assert json.loads(snap.read_text()) == json.loads(json.dumps(client.app.openapi())), \
        "API changed: review it, then run `python -m scripts.export_openapi` and commit the snapshot"


def test_encryption_key_rotation(monkeypatch):
    from cryptography.fernet import Fernet
    from app.core.config import get_settings
    from app.core.crypto import decrypt, encrypt
    old, new = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    cfg = get_settings()
    monkeypatch.setattr(cfg, "encryption_key", old)
    blob = encrypt("secret-ref")
    monkeypatch.setattr(cfg, "encryption_key", f"{new},{old}")  # rotation: new key first, old kept for decrypting
    assert decrypt(blob) == "secret-ref"
    fresh = encrypt("another")
    monkeypatch.setattr(cfg, "encryption_key", new)  # old key retired: old blobs unreadable, new ones fine
    assert decrypt(fresh) == "another"
    import pytest
    from cryptography.fernet import InvalidToken
    with pytest.raises(InvalidToken):
        decrypt(blob)

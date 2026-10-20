import hashlib, hmac, json, os, tempfile, time
from urllib.parse import urlencode
import pytest

TOKEN = "123456:TEST-BOT-TOKEN"
from cryptography.fernet import Fernet  # noqa: E402
os.environ.update(WORKER_API_TOKEN="worker-secret-token", ENCRYPTION_KEY=Fernet.generate_key().decode(),
                  IMPORT_ALLOWED_HOSTS="media.example", JOB_MAX_ATTEMPTS="3", RETRY_BACKOFF_SECONDS="60")
os.environ.update(TELEGRAM_BOT_TOKEN=TOKEN, JWT_SIGNING_KEY="x" * 40, BOT_API_TOKEN="bot-secret-token", BOT_USERNAME="ShoflyBot", CORS_ORIGINS="https://shofly.example", APP_ENV="test",
                  DATABASE_URL=os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{tempfile.mkdtemp()}/t.db")

from fastapi.testclient import TestClient  # noqa: E402
from app.core.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402


def make_init_data(user: dict, auth_date: int | None = None, token: str = TOKEN, tamper: bool = False) -> str:
    fields = {"auth_date": str(auth_date or int(time.time())), "user": json.dumps(user)}
    check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if tamper:
        fields["user"] = json.dumps({**user, "id": user["id"] + 1})
    return urlencode(fields)


@pytest.fixture(autouse=True)
def fresh_db():
    from app.core.ratelimit import limiter; limiter.reset()
    Base.metadata.drop_all(engine); Base.metadata.create_all(engine)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def db():
    with SessionLocal() as s:
        yield s


def login(client, user):
    r = client.post("/api/v1/auth/telegram", json={"init_data": make_init_data(user)})
    assert r.status_code == 200, r.text
    return r.json()

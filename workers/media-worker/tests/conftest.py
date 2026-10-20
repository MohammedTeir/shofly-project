import os, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "backend"))
from cryptography.fernet import Fernet  # noqa: E402
os.environ.update(TELEGRAM_BOT_TOKEN="123456:TEST", JWT_SIGNING_KEY="x" * 40, WORKER_API_TOKEN="worker-secret-token",
                  ENCRYPTION_KEY=Fernet.generate_key().decode(), IMPORT_ALLOWED_HOSTS="media.example", APP_ENV="test",
                  DATABASE_URL=os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{tempfile.mkdtemp()}/w.db", JOB_MAX_ATTEMPTS="3", RETRY_BACKOFF_SECONDS="60")
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from app.core.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app as backend_app  # noqa: E402

PUBLIC = lambda host, port, type=None: [(2, 1, 6, "", ("93.184.216.34", 443))]


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine); Base.metadata.create_all(engine)


@pytest.fixture
def db():
    with SessionLocal() as s:
        yield s


@pytest.fixture
def api():
    return TestClient(backend_app)

import os, sys, tempfile
from cryptography.fernet import Fernet
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "backend"))
os.environ.update(TELEGRAM_BOT_TOKEN="123456:TESTTOKEN", JWT_SIGNING_KEY="x" * 40, BOT_API_TOKEN="bot-secret-token", BOT_USERNAME="ShoflyBot", ENCRYPTION_KEY=Fernet.generate_key().decode(),
                  APP_ENV="test", DATABASE_URL=os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{tempfile.mkdtemp()}/b.db")
import httpx, pytest  # noqa: E402
from app.core.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app as backend_app  # noqa: E402
from tgbot.api import BotApi  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine); Base.metadata.create_all(engine)


@pytest.fixture
def db():
    with SessionLocal() as s:
        yield s


@pytest.fixture
def make_api():
    return lambda token="bot-secret-token": BotApi("http://test", token, transport=httpx.ASGITransport(app=backend_app))

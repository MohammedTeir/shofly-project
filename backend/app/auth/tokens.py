import time, uuid
import jwt
from app.core.config import get_settings
from app.core.errors import AppError


def issue_token(user_id: uuid.UUID) -> tuple[str, int]:
    s = get_settings()
    ttl = s.access_token_ttl_seconds
    now = int(time.time())
    return jwt.encode({"sub": str(user_id), "iat": now, "exp": now + ttl}, s.jwt_signing_key, algorithm="HS256"), ttl


def decode_token(token: str) -> uuid.UUID:
    try:
        data = jwt.decode(token, get_settings().jwt_signing_key, algorithms=["HS256"])
        return uuid.UUID(data["sub"])
    except Exception:
        raise AppError(401, "INVALID_TOKEN", "Authentication required.")

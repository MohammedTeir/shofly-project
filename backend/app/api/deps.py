import hmac
from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from app.auth.tokens import decode_token
from app.core.config import get_settings
from app.core.db import get_db
from app.core.errors import AppError
from app.models import User

bearer = HTTPBearer(auto_error=False)


def current_user(cred: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)) -> User:
    if cred is None:
        raise AppError(401, "AUTH_REQUIRED", "Authentication required.")
    user = db.get(User, decode_token(cred.credentials))
    if user is None or user.status != "active":
        raise AppError(401, "INVALID_TOKEN", "Authentication required.")
    return user


def require_role(*roles: str):
    def dep(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise AppError(403, "FORBIDDEN", "Permission denied.")
        return user
    return dep


def worker_auth(x_worker_token: str | None = Header(None)) -> None:
    """Worker credential only reaches /worker/* routes; it grants no user or admin powers."""
    tok = get_settings().worker_api_token
    if not tok:
        raise AppError(503, "WORKER_AUTH_DISABLED", "Worker authentication is not configured.")
    if not x_worker_token or not hmac.compare_digest(x_worker_token, tok):
        raise AppError(401, "INVALID_WORKER_TOKEN", "Authentication required.")


def require_bot_token(x_bot_token: str | None = Header(None)) -> None:
    """Shared secret between the backend and the bot process. Never exposed to clients."""
    tok = get_settings().bot_api_token
    if not tok:
        raise AppError(503, "BOT_AUTH_DISABLED", "Bot authentication is not configured.")
    if not x_bot_token or not hmac.compare_digest(x_bot_token, tok):
        raise AppError(401, "INVALID_BOT_TOKEN", "Authentication required.")

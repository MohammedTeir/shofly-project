from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.api.routes_auth import LoginOut, UserOut
from app.auth.tokens import issue_token
from app.api.deps import require_bot_token
from app.core.db import get_db
from app.core.errors import AppError
from app.users import get_or_create_user

router = APIRouter()


class BotUser(BaseModel):
    id: int
    is_bot: bool = False
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    language_code: str | None = None


@router.post("/bot/auth", response_model=LoginOut)
def bot_auth(body: BotUser, x_bot_token: str | None = Header(None), db: Session = Depends(get_db)):
    """Server-to-server login for the bot process. The bot is trusted to pass the *verified* Telegram
    update sender (AUTH-03); the shared secret must never reach any client."""
    require_bot_token(x_bot_token)
    if body.is_bot:
        raise AppError(400, "BAD_REQUEST", "Bots cannot register.")
    user = get_or_create_user(db, body.model_dump())
    if user.status != "active":
        raise AppError(403, "FORBIDDEN", "Account disabled.")
    token, ttl = issue_token(user.id)
    return LoginOut(access_token=token, expires_in=ttl, user=UserOut.model_validate(user))

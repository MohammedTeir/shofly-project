import uuid
from datetime import datetime
from fastapi import APIRouter, Depends
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session
from app.api.deps import current_user
from app.auth.telegram import verify_init_data
from app.auth.tokens import issue_token
from app.core.config import get_settings
from app.core.db import get_db
from app.core.ratelimit import rate_limit
from app.models import User
from app.users import get_or_create_user, set_language

router = APIRouter()


class TelegramLogin(BaseModel):
    init_data: str


class UserOut(BaseModel):
    id: uuid.UUID
    telegram_id: int
    preferred_language: str
    language_source: str | None
    role: str
    model_config = {"from_attributes": True}


class LoginOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


class PrefsIn(BaseModel):
    preferred_language: str

    @field_validator("preferred_language")
    @classmethod
    def supported(cls, v: str) -> str:
        if v not in get_settings().languages:
            raise ValueError("unsupported language")
        return v


class PrefsOut(BaseModel):
    preferred_language: str
    language_source: str
    updated_at: datetime


@router.post("/auth/telegram", response_model=LoginOut, dependencies=[Depends(rate_limit("auth", 20))])
def telegram_login(body: TelegramLogin, db: Session = Depends(get_db)):
    s = get_settings()
    tg = verify_init_data(body.init_data, s.telegram_bot_token, s.initdata_max_age_seconds)
    user = get_or_create_user(db, tg)
    token, ttl = issue_token(user.id)
    return LoginOut(access_token=token, expires_in=ttl, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user


@router.patch("/me/preferences", response_model=PrefsOut)
def update_prefs(body: PrefsIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    user = set_language(db, user, body.preferred_language)
    return PrefsOut(preferred_language=user.preferred_language, language_source="user", updated_at=user.language_updated_at)

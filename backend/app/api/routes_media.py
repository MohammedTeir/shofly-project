import uuid
import time
import jwt
from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session
from app.api.deps import current_user, require_bot_token
from app.audit import audit
from app.core.config import get_settings
from app.core.crypto import decrypt
from app.core.db import get_db
from app.core.errors import AppError
from app.core.ratelimit import rate_limit
from app.delivery import evaluate_asset
from app.models import User

router = APIRouter(prefix="/media", dependencies=[Depends(rate_limit("media", 30))])


@router.post("/{asset_id}/access")
def access(asset_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """For the Mini App: returns an opaque bot deep link. No storage reference ever leaves the backend here."""
    asset = evaluate_asset(db, user, asset_id)
    bot = get_settings().bot_username
    if not bot:
        raise AppError(503, "BOT_NOT_CONFIGURED", "Delivery bot is not configured.")
    return {"delivery_type": "telegram_bot", "bot_deep_link": f"https://t.me/{bot}?start=dl_{asset.id.hex}"}


@router.post("/{asset_id}/telegram-delivery", dependencies=[Depends(require_bot_token)])
def telegram_delivery(asset_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Bot-only: needs the shared bot secret AND the user's own token. Re-checks the full policy and audits the delivery."""
    asset = evaluate_asset(db, user, asset_id)
    try:
        chat, message, _ = decrypt(asset.provider_ref_encrypted).split(":", 2)
        ref = {"chat_id": int(chat), "message_id": int(message)}
    except (ValueError, TypeError):
        raise AppError(400, "MEDIA_DELIVERY_UNSUPPORTED", "Delivery is not supported for this file.")
    segments = []
    for encrypted in (asset.segment_refs_encrypted or []):
        try:
            part_chat, part_message, _ = decrypt(encrypted).split(":", 2)
            segments.append({"chat_id": int(part_chat), "message_id": int(part_message)})
        except (ValueError, TypeError):
            raise AppError(400, "MEDIA_DELIVERY_UNSUPPORTED", "Invalid segment reference.")
    if segments and segments[0] != ref:
        raise AppError(409, "MEDIA_SEGMENT_MISMATCH", "Segment references are inconsistent.")
    if segments:
        ref["parts"] = segments
        ref["part_count"] = len(segments)
    audit(db, user.id, "media.deliver", "media_asset", asset.id, {"platform": "telegram"})
    db.commit()
    return ref


@router.post("/{asset_id}/playback")
def playback(asset_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Issue short-lived playback capability; storage identifiers stay server-side."""
    settings = get_settings()
    if not settings.streaming_gateway_url or not settings.streaming_signing_key:
        raise AppError(503, "STREAMING_NOT_CONFIGURED", "Streaming gateway is not configured.")
    asset = evaluate_asset(db, user, asset_id)
    if asset.provider != "telegram" or asset.segment_refs_encrypted:
        raise AppError(400, "STREAMING_UNSUPPORTED", "This asset requires Telegram delivery.")
    now = int(time.time())
    ticket = jwt.encode({"sub": str(user.id), "asset": str(asset.id), "aud": "shofly-stream",
                         "iat": now, "exp": now + 14400}, settings.streaming_signing_key, algorithm="HS256")
    return {"playback_url": settings.streaming_gateway_url.rstrip("/") + "/stream/" + str(asset.id) + "?ticket=" + ticket,
            "expires_in": 14400}


@router.post("/{asset_id}/stream-authorize")
def stream_authorize(asset_id: uuid.UUID, payload: dict, db: Session = Depends(get_db),
                     x_streaming_secret: str | None = Header(None)):
    """Gateway-only, fresh entitlement/rights check for every range request."""
    import hmac
    settings = get_settings()
    if not settings.streaming_internal_secret or not x_streaming_secret or not hmac.compare_digest(
        x_streaming_secret, settings.streaming_internal_secret
    ):
        raise AppError(401, "UNAUTHORIZED", "Authentication required.")
    try:
        claims = jwt.decode(payload.get("ticket", ""), settings.streaming_signing_key,
                            algorithms=["HS256"], audience="shofly-stream")
        if claims.get("asset") != str(asset_id):
            raise ValueError("asset mismatch")
        user = db.get(User, uuid.UUID(claims["sub"]))
        if user is None or user.status != "active":
            raise ValueError("inactive user")
    except (jwt.PyJWTError, ValueError, TypeError, KeyError):
        raise AppError(401, "INVALID_PLAYBACK_TICKET", "Playback authorization expired.")
    asset = evaluate_asset(db, user, asset_id)
    if asset.provider != "telegram" or asset.segment_refs_encrypted:
        raise AppError(400, "STREAMING_UNSUPPORTED", "This asset requires Telegram delivery.")
    try:
        chat, message, _ = decrypt(asset.provider_ref_encrypted).split(":", 2)
        return {"chat_id": int(chat), "message_id": int(message)}
    except (ValueError, TypeError):
        raise AppError(400, "STREAMING_UNSUPPORTED", "Invalid storage reference.")

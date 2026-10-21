import uuid
from fastapi import APIRouter, Depends
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

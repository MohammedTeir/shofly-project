"""Delivery policy (spec 9.3), evaluated server-side on every access request, never cached:
 authenticated AND active AND published AND verified asset AND rights valid now AND platform allowed
 AND territory allowed AND entitlement. Denials never reveal storage details."""
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.core.errors import AppError
from app.imports.service import as_utc
from app.models import ContentRight, Episode, MediaAsset, Movie, Season, TvSeries, User

PROVIDER_PLATFORM = {"telegram": "telegram"}  # object-storage/web streaming providers are not built yet
FLAG = {"telegram": "telegram_allowed", "web": "web_allowed"}
STATUS = {"MEDIA_DELIVERY_UNSUPPORTED": 400, "RIGHTS_NOT_AVAILABLE": 403, "TERRITORY_RESTRICTED": 403, "ENTITLEMENT_REQUIRED": 403}
MESSAGE = {"MEDIA_DELIVERY_UNSUPPORTED": "Delivery is not supported for this file.", "RIGHTS_NOT_AVAILABLE": "This title is not available.",
           "TERRITORY_RESTRICTED": "This title is not available in your region.", "ENTITLEMENT_REQUIRED": "A subscription is required."}


def territory_ok(territories, user_territory: str | None) -> bool:
    """Unknown user territory is never guessed: only worldwide ('ALL') licenses pass."""
    t = territories or []
    return "ALL" in t or (user_territory is not None and user_territory in t)


def entitlement_ok(user: User, asset: MediaAsset) -> bool:
    # Billing is off (BILLING_ENABLED=false): everything is free. Premium gating arrives with the subscriptions milestone.
    return not get_settings().billing_enabled


def check(user: User, asset: MediaAsset, rights: list[ContentRight], now: datetime, user_territory: str | None = None) -> str | None:
    platform = PROVIDER_PLATFORM.get(asset.provider)
    if platform is None:
        return "MEDIA_DELIVERY_UNSUPPORTED"
    valid = [r for r in rights if r.review_status == "APPROVED" and as_utc(r.valid_from) <= now <= as_utc(r.valid_until)]
    allowed = [r for r in valid if getattr(r, FLAG[platform])]
    if not allowed:
        return "RIGHTS_NOT_AVAILABLE"
    if not any(territory_ok(r.territories, user_territory) for r in allowed):
        return "TERRITORY_RESTRICTED"
    if not entitlement_ok(user, asset):
        return "ENTITLEMENT_REQUIRED"
    return None


def _rights(db: Session, kind: str, ids) -> dict[uuid.UUID, list[ContentRight]]:
    out = defaultdict(list)
    for r in db.scalars(select(ContentRight).where(ContentRight.content_kind == kind, ContentRight.content_id.in_(list(ids)))):
        out[r.content_id].append(r)
    return out


def _published(db: Session, asset: MediaAsset) -> bool:
    if asset.movie_id:
        return db.scalar(select(Movie.id).where(Movie.id == asset.movie_id, Movie.status == "published")) is not None
    return db.scalar(select(TvSeries.id).join(Season, Season.series_id == TvSeries.id).join(Episode, Episode.season_id == Season.id)
                     .where(Episode.id == asset.episode_id, TvSeries.status == "published")) is not None


def evaluate_asset(db: Session, user: User, asset_id: uuid.UUID) -> MediaAsset:
    asset = db.get(MediaAsset, asset_id)
    if asset is None or asset.upload_status != "verified" or not _published(db, asset):
        raise AppError(404, "NOT_FOUND", "Not found.")  # unpublished/unverified content is indistinguishable from missing
    kind, tid = ("movie", asset.movie_id) if asset.movie_id else ("episode", asset.episode_id)
    code = check(user, asset, _rights(db, kind, [tid]).get(tid, []), datetime.now(timezone.utc))
    if code:
        raise AppError(STATUS[code], code, MESSAGE[code])
    return asset


def deliverable_assets(db: Session, user: User, kind: str, ids: list[uuid.UUID]) -> dict[uuid.UUID, list[dict]]:
    """Assets a viewer may actually receive, grouped by movie/episode id (bulk: no per-row queries)."""
    if not ids:
        return {}
    col = MediaAsset.movie_id if kind == "movie" else MediaAsset.episode_id
    rights, now, out = _rights(db, kind, ids), datetime.now(timezone.utc), defaultdict(list)
    for a in db.scalars(select(MediaAsset).where(col.in_(ids), MediaAsset.upload_status == "verified").order_by(MediaAsset.size_bytes.desc())):
        tid = a.movie_id or a.episode_id
        if check(user, a, rights.get(tid, []), now) is None:
            out[tid].append({"id": a.id, "quality": a.quality, "audio_language": a.audio_language,
                             "duration_sec": a.duration_sec, "size_bytes": a.size_bytes})
    return out

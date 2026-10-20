"""Single source of truth for 'can members see/receive this?': published AND a verified asset AND approved, in-window rights.
Evaluated at query time, so expiry/revocation hides content immediately with no background job."""
import uuid
from datetime import datetime, timezone
from sqlalchemy import and_, exists, or_, select
from sqlalchemy.orm import Session
from app.models import ContentRight, Episode, MediaAsset, Movie, Season, TvSeries


def _now(): return datetime.now(timezone.utc)


def _right(kind: str, id_col, now):
    return exists().where(ContentRight.content_kind == kind, ContentRight.content_id == id_col,
                          ContentRight.review_status == "APPROVED", ContentRight.valid_from <= now, ContentRight.valid_until >= now,
                          or_(ContentRight.telegram_allowed.is_(True), ContentRight.web_allowed.is_(True)))


def _asset(col, id_col):
    return exists().where(col == id_col, MediaAsset.upload_status == "verified")


def visible_clause(kind: str, now: datetime | None = None):
    now = now or _now()
    if kind == "movie":
        return and_(Movie.status == "published", _asset(MediaAsset.movie_id, Movie.id), _right("movie", Movie.id, now))
    ep_ok = exists().where(Season.series_id == TvSeries.id, Episode.season_id == Season.id,
                           _asset(MediaAsset.episode_id, Episode.id), _right("episode", Episode.id, now))
    return and_(TvSeries.status == "published", ep_ok)


def is_visible(db: Session, kind: str, item_id: uuid.UUID) -> bool:
    model = Movie if kind == "movie" else TvSeries
    return db.scalar(select(model.id).where(model.id == item_id, visible_clause(kind))) is not None


def deliverable_episode_ids(db: Session, series_id: uuid.UUID) -> list[uuid.UUID]:
    now = _now()
    return list(db.scalars(select(Episode.id).join(Season, Season.id == Episode.season_id).where(
        Season.series_id == series_id, _asset(MediaAsset.episode_id, Episode.id), _right("episode", Episode.id, now))))


def blockers(db: Session, kind: str, item) -> list[str]:
    """Why this title cannot be published right now (empty list = OK)."""
    b = [] if item.metadata_verified else ["METADATA_NOT_VERIFIED"]
    if kind == "movie":
        if db.scalar(select(MediaAsset.id).where(MediaAsset.movie_id == item.id, MediaAsset.upload_status == "verified").limit(1)) is None:
            b.append("NO_VERIFIED_ASSET")
        if db.scalar(select(Movie.id).where(Movie.id == item.id, _right("movie", Movie.id, _now()))) is None:
            b.append("RIGHTS_NOT_VALID")
    elif not deliverable_episode_ids(db, item.id):
        b.append("NO_DELIVERABLE_EPISODE")
    return b

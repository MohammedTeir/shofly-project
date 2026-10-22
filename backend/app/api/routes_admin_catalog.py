import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Literal
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select, delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.api.deps import require_role
from app.audit import audit
from app.catalog.service import KINDS
from app.core.db import get_db
from app.core.errors import AppError
from app.models import (CollectionMovie, ContentRight, Episode, Favorite, ImportJob, LocalizedMetadata, MediaAsset, Movie, Season, TvSeries, User)
from app.publishing import blockers, deliverable_episode_ids
from app.users import ROLES

router = APIRouter(prefix="/admin")
staff = require_role("content_admin", "super_admin")
Kind = Literal["movie", "series"]


def _item(db: Session, kind: str, item_id: uuid.UUID):
    it = db.get(KINDS[kind], item_id)
    if it is None:
        raise AppError(404, "NOT_FOUND", "Not found.")
    return it


def _commit(db: Session, what: str):
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AppError(409, "CONFLICT", f"{what} already exists.")


@router.get("/overview")
def overview(admin: User = Depends(staff), db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)

    def counts(model):
        rows = dict(db.execute(select(model.status, func.count()).group_by(model.status)).all())
        return {"total": sum(rows.values()), "published": rows.get("published", 0), "draft": rows.get("draft", 0)}
    jobs = dict(db.execute(select(ImportJob.status, func.count()).group_by(ImportJob.status)).all())
    expiring = db.scalar(select(func.count()).select_from(ContentRight).where(
        ContentRight.review_status == "APPROVED", ContentRight.valid_until >= now, ContentRight.valid_until <= now + timedelta(days=14)))
    pending = db.scalar(select(func.count()).select_from(ContentRight).where(ContentRight.review_status == "PENDING"))
    return {"movies": counts(Movie), "series": counts(TvSeries), "jobs": jobs, "rights_expiring_14d": expiring,
            "rights_pending": pending, "users": db.scalar(select(func.count()).select_from(User))}


@router.get("/catalog/{kind}")
def list_items(kind: Kind, q: str | None = None, status: Literal["draft", "published"] | None = None,
               cursor: int = Query(0, ge=0), limit: int = Query(30, ge=1, le=100),
               admin: User = Depends(staff), db: Session = Depends(get_db)):
    m = KINDS[kind]
    stmt = select(m)
    if q:
        stmt = stmt.where(m.original_title.ilike(f"%{q}%"))
    if status:
        stmt = stmt.where(m.status == status)
    rows = list(db.scalars(stmt.order_by(m.created_at.desc(), m.id).offset(cursor).limit(limit + 1)))
    return {"items": [{"id": r.id, "kind": kind, "title": r.original_title, "year": getattr(r, "release_year", None),
                       "status": r.status, "metadata_verified": r.metadata_verified} for r in rows[:limit]],
            "next_cursor": str(cursor + limit) if len(rows) > limit else None}


@router.get("/catalog/{kind}/{item_id}")
def detail(kind: Kind, item_id: uuid.UUID, admin: User = Depends(staff), db: Session = Depends(get_db)):
    it = _item(db, kind, item_id)
    out = {"id": it.id, "kind": kind, "original_title": it.original_title, "status": it.status,
           "year": getattr(it, "release_year", None), "metadata_verified": it.metadata_verified,
           "blockers": blockers(db, kind, it),
           "translations": [{"language": t.language_code, "title": t.title} for t in db.scalars(
               select(LocalizedMetadata).where(LocalizedMetadata.content_kind == kind, LocalizedMetadata.content_id == it.id))]}
    target_ids: list[uuid.UUID] = [it.id]
    if kind == "series":
        eps = db.execute(select(Episode, Season.season_number).join(Season, Season.id == Episode.season_id)
                         .where(Season.series_id == it.id).order_by(Season.season_number, Episode.episode_number)).all()
        ok = set(deliverable_episode_ids(db, it.id))
        out["episodes"] = [{"id": e.id, "season_number": sn, "episode_number": e.episode_number, "title": e.title,
                            "deliverable": e.id in ok} for e, sn in eps]
        out["seasons"] = [{"id": s.id, "season_number": s.season_number} for s in db.scalars(
            select(Season).where(Season.series_id == it.id).order_by(Season.season_number))]
        target_ids = [e.id for e, _ in eps]
    col = MediaAsset.movie_id if kind == "movie" else MediaAsset.episode_id
    out["assets"] = [{"id": a.id, "target_id": a.movie_id or a.episode_id, "quality": a.quality, "codec": a.codec, "provider": a.provider,
                      "size_bytes": a.size_bytes, "duration_sec": a.duration_sec, "upload_status": a.upload_status}
                     for a in db.scalars(select(MediaAsset).where(col.in_(target_ids)))] if target_ids else []
    rk = "movie" if kind == "movie" else "episode"
    out["rights"] = [{"id": r.id, "content_id": r.content_id, "review_status": r.review_status, "license_type": r.license_type,
                      "valid_from": r.valid_from, "valid_until": r.valid_until, "telegram_allowed": r.telegram_allowed,
                      "web_allowed": r.web_allowed} for r in db.scalars(
        select(ContentRight).where(ContentRight.content_kind == rk, ContentRight.content_id.in_(target_ids)))] if target_ids else []
    return out


@router.post("/catalog/{kind}/{item_id}/verify-metadata")
def verify_metadata(kind: Kind, item_id: uuid.UUID, admin: User = Depends(staff), db: Session = Depends(get_db)):
    it = _item(db, kind, item_id)
    it.metadata_verified = True
    audit(db, admin.id, "metadata.verify", kind, it.id)
    db.commit()
    return {"metadata_verified": True}


@router.post("/catalog/{kind}/{item_id}/publish")
def publish(kind: Kind, item_id: uuid.UUID, admin: User = Depends(staff), db: Session = Depends(get_db)):
    it = _item(db, kind, item_id)
    b = blockers(db, kind, it)
    if b:  # no bypass: metadata verified + verified asset + approved in-window rights
        raise AppError(409, "PUBLISH_BLOCKED", "Title does not meet the publishing requirements.", {"blockers": b})
    it.status = "published"
    audit(db, admin.id, "catalog.publish", kind, it.id)
    db.commit()
    return {"status": it.status}


@router.post("/catalog/{kind}/{item_id}/unpublish")
def unpublish(kind: Kind, item_id: uuid.UUID, admin: User = Depends(staff), db: Session = Depends(get_db)):
    it = _item(db, kind, item_id)
    it.status = "draft"  # takedown: effective on the very next request
    audit(db, admin.id, "catalog.unpublish", kind, it.id)
    db.commit()
    return {"status": it.status}


class SeasonIn(BaseModel):
    season_number: int = Field(ge=0, le=999)  # 0 = specials
    title: str | None = Field(None, max_length=300)


class EpisodeIn(BaseModel):
    episode_number: int = Field(ge=1, le=9999)
    title: str | None = Field(None, max_length=500)
    air_date: date | None = None


@router.post("/catalog/series/{series_id}/seasons", status_code=201)
def add_season(series_id: uuid.UUID, body: SeasonIn, admin: User = Depends(staff), db: Session = Depends(get_db)):
    _item(db, "series", series_id)
    s = Season(id=uuid.uuid4(), series_id=series_id, **body.model_dump())
    db.add(s)
    audit(db, admin.id, "season.create", "series", series_id, {"season": body.season_number})
    _commit(db, "Season")
    return {"id": s.id}


@router.post("/catalog/seasons/{season_id}/episodes", status_code=201)
def add_episode(season_id: uuid.UUID, body: EpisodeIn, admin: User = Depends(staff), db: Session = Depends(get_db)):
    s = db.get(Season, season_id)
    if s is None:
        raise AppError(404, "NOT_FOUND", "Not found.")
    e = Episode(id=uuid.uuid4(), season_id=season_id, **body.model_dump())
    db.add(e)
    audit(db, admin.id, "episode.create", "series", s.series_id, {"episode": body.episode_number})
    _commit(db, "Episode")
    return {"id": e.id}


# ---- users (super admin only, ADM-09) ----
su = require_role("super_admin")


class UserPatch(BaseModel):
    role: str | None = None
    status: Literal["active", "suspended"] | None = None


@router.get("/users")
def users(q: str | None = None, cursor: int = Query(0, ge=0), limit: int = Query(30, ge=1, le=100),
          admin: User = Depends(su), db: Session = Depends(get_db)):
    stmt = select(User)
    if q:
        stmt = stmt.where(User.username.ilike(f"%{q}%") | User.display_name.ilike(f"%{q}%"))
    rows = list(db.scalars(stmt.order_by(User.created_at.desc(), User.id).offset(cursor).limit(limit + 1)))
    return {"items": [{"id": u.id, "telegram_id": u.telegram_id, "username": u.username, "display_name": u.display_name,
                       "role": u.role, "status": u.status, "preferred_language": u.preferred_language} for u in rows[:limit]],
            "next_cursor": str(cursor + limit) if len(rows) > limit else None}


@router.patch("/users/{user_id}")
def patch_user(user_id: uuid.UUID, body: UserPatch, admin: User = Depends(su), db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if u is None:
        raise AppError(404, "NOT_FOUND", "Not found.")
    if u.id == admin.id:
        raise AppError(409, "CANNOT_EDIT_SELF", "You cannot change your own role or status.")
    if body.role is not None and body.role not in ROLES:
        raise AppError(422, "VALIDATION_ERROR", "Unknown role.")
    before = {"role": u.role, "status": u.status}
    if body.role is not None: u.role = body.role
    if body.status is not None: u.status = body.status
    audit(db, admin.id, "user.update", "user", u.id, {"before": before, "after": {"role": u.role, "status": u.status}})
    db.commit()
    return {"id": u.id, "role": u.role, "status": u.status}


@router.post("/catalog/movie/{item_id}/delete-all")
def delete_movie_all(item_id: uuid.UUID, admin: User = Depends(staff), db: Session = Depends(get_db)):
    """Stage complete deletion. Telegram removal is performed by the MTProto worker."""
    movie = db.scalar(select(Movie).where(Movie.id == item_id).with_for_update())
    if movie is None:
        raise AppError(404, "NOT_FOUND", "Movie not found.")
    jobs = list(db.scalars(select(ImportJob).where(ImportJob.candidate_kind == "movie", ImportJob.target_id == item_id)))
    active = [j for j in jobs if j.status in ("DOWNLOADING", "PROBING", "PROCESSING", "UPLOADING", "VERIFYING")]
    if active:
        raise AppError(409, "IMPORT_ACTIVE", "Wait for running imports to finish or cancel them first.")
    assets = list(db.scalars(select(MediaAsset).where(MediaAsset.movie_id == item_id).with_for_update()))
    if any(a.provider != "telegram" and a.upload_status != "deleted" for a in assets):
        raise AppError(409, "UNSUPPORTED_PROVIDER", "Non-Telegram storage requires manual cleanup.")
    movie.status = "deleting"
    for a in assets:
        if a.upload_status not in ("deleted", "cleanup_processing"):
            a.upload_status = "cleanup_pending"
    audit(db, admin.id, "movie.delete_all_requested", "movie", item_id,
          {"assets": len(assets), "jobs": len(jobs)})
    db.commit()
    return {"status": "deleting", "assets": len(assets), "jobs": len(jobs),
            "message": "Run MTProto worker to remove Telegram files and finalize deletion."}


def finalize_deleted_movie(db: Session, movie_id: uuid.UUID) -> bool:
    movie = db.scalar(select(Movie).where(Movie.id == movie_id).with_for_update())
    if movie is None or movie.status != "deleting":
        return False
    assets = list(db.scalars(select(MediaAsset).where(MediaAsset.movie_id == movie_id)))
    if any(a.upload_status != "deleted" for a in assets):
        return False
    jobs = list(db.scalars(select(ImportJob).where(ImportJob.candidate_kind == "movie", ImportJob.target_id == movie_id)))
    for a in assets:
        db.delete(a)
    db.flush()
    for j in jobs:
        db.delete(j)
    db.execute(delete(CollectionMovie).where(CollectionMovie.movie_id == movie_id))
    db.execute(delete(Favorite).where(Favorite.content_kind == "movie", Favorite.content_id == movie_id))
    db.execute(delete(LocalizedMetadata).where(LocalizedMetadata.content_kind == "movie", LocalizedMetadata.content_id == movie_id))
    db.execute(delete(ContentRight).where(ContentRight.content_kind == "movie", ContentRight.content_id == movie_id))
    db.delete(movie)
    audit(db, None, "movie.delete_all_completed", "movie", movie_id,
          {"assets": len(assets), "jobs": len(jobs)})
    return True

import uuid
from typing import Literal
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.api.deps import require_role
from app.audit import audit
from app.catalog.service import KINDS
from app.core.config import get_settings
from app.core.db import get_db
from app.core.errors import AppError
from app.models import AuditLog, CollectionMovie, LocalizedMetadata, Movie, MovieCollection, TvSeries, User

router = APIRouter(prefix="/admin")
staff = require_role("content_admin", "super_admin")


class MovieIn(BaseModel):
    original_title: str = Field(min_length=1, max_length=500)
    original_language: str | None = None
    release_year: int | None = Field(None, ge=1888, le=2200)
    tmdb_id: int | None = None


class SeriesIn(BaseModel):
    original_title: str = Field(min_length=1, max_length=500)
    original_language: str | None = None
    tmdb_id: int | None = None


class CollectionIn(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    tmdb_collection_id: int | None = None
    movie_ids: list[uuid.UUID] = []


class TranslationIn(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    synopsis: str | None = None


def _commit(db: Session, what: str):
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AppError(409, "CONFLICT", f"{what} already exists.")


# NOTE: no publish endpoint yet. Publishing requires approved rights + verified asset (Milestones 4/6),
# so everything created here stays 'draft' and is invisible to members.
@router.post("/catalog/movies", status_code=201)
def create_movie(body: MovieIn, admin: User = Depends(staff), db: Session = Depends(get_db)):
    m = Movie(id=uuid.uuid4(), **body.model_dump(), status="draft")
    db.add(m)
    audit(db, admin.id, "movie.create", "movie", m.id, {"tmdb_id": body.tmdb_id})
    _commit(db, "Movie")
    return {"id": m.id, "status": m.status}


@router.post("/catalog/series", status_code=201)
def create_series(body: SeriesIn, admin: User = Depends(staff), db: Session = Depends(get_db)):
    s = TvSeries(id=uuid.uuid4(), **body.model_dump(), status="draft")
    db.add(s)
    audit(db, admin.id, "series.create", "series", s.id, {"tmdb_id": body.tmdb_id})
    _commit(db, "Series")
    return {"id": s.id, "status": s.status}


@router.post("/catalog/collections", status_code=201)
def create_collection(body: CollectionIn, admin: User = Depends(staff), db: Session = Depends(get_db)):
    if len(set(body.movie_ids)) != len(body.movie_ids):
        raise AppError(422, "VALIDATION_ERROR", "Duplicate movie in collection.")
    found = set(db.scalars(select(Movie.id).where(Movie.id.in_(body.movie_ids)))) if body.movie_ids else set()
    if found != set(body.movie_ids):
        raise AppError(404, "NOT_FOUND", "One or more movies do not exist.")
    c = MovieCollection(id=uuid.uuid4(), name=body.name, tmdb_collection_id=body.tmdb_collection_id)
    db.add(c)
    db.flush()
    for i, mid in enumerate(body.movie_ids):
        db.add(CollectionMovie(collection_id=c.id, movie_id=mid, sort_order=i))
    audit(db, admin.id, "collection.create", "collection", c.id, {"count": len(body.movie_ids)})
    _commit(db, "Collection")
    return {"id": c.id}


@router.put("/catalog/{kind}/{item_id}/translations/{lang}")
def put_translation(kind: Literal["movie", "series"], item_id: uuid.UUID, lang: str, body: TranslationIn,
                    admin: User = Depends(staff), db: Session = Depends(get_db)):
    if lang not in get_settings().languages:
        raise AppError(422, "VALIDATION_ERROR", "Unsupported language.")
    if db.get(KINDS[kind], item_id) is None:
        raise AppError(404, "NOT_FOUND", "Not found.")
    row = db.scalar(select(LocalizedMetadata).where(LocalizedMetadata.content_kind == kind,
                    LocalizedMetadata.content_id == item_id, LocalizedMetadata.language_code == lang))
    if row:
        row.title, row.synopsis = body.title, body.synopsis
    else:
        db.add(LocalizedMetadata(content_kind=kind, content_id=item_id, language_code=lang,
                                 title=body.title, synopsis=body.synopsis, source="manual"))
    audit(db, admin.id, "translation.upsert", kind, item_id, {"lang": lang})
    _commit(db, "Translation")
    return {"ok": True}


@router.get("/audit-logs")
def audit_logs(limit: int = Query(50, ge=1, le=200), admin: User = Depends(require_role("super_admin")),
               db: Session = Depends(get_db)):
    rows = db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit))
    return {"items": [{"id": r.id, "actor_id": r.actor_id, "action": r.action, "entity_kind": r.entity_kind,
                       "entity_id": r.entity_id, "created_at": r.created_at} for r in rows]}

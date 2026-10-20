import uuid
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.deps import current_user
from app.catalog.service import list_titles
from app.core.db import get_db
from app.core.errors import AppError
from app.models import Episode, Season, User
from app.delivery import deliverable_assets
from app.publishing import is_visible

router = APIRouter(prefix="/catalog")


def _page(db, kind, user, q, cursor, limit):
    items, nxt = list_titles(db, kind, user.preferred_language, q, cursor, limit)
    return {"items": items, "next_cursor": str(nxt) if nxt is not None else None}


@router.get("/movies")
def movies(q: str | None = None, cursor: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=50),
           user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _page(db, "movie", user, q, cursor, limit)


@router.get("/series")
def series(q: str | None = None, cursor: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=50),
           user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _page(db, "series", user, q, cursor, limit)


@router.get("/search")
def search(q: str = Query(min_length=1, max_length=100), limit: int = Query(20, ge=1, le=50),
           user: User = Depends(current_user), db: Session = Depends(get_db)):
    m, _ = list_titles(db, "movie", user.preferred_language, q, 0, limit)
    s, _ = list_titles(db, "series", user.preferred_language, q, 0, limit)
    return {"items": m + s}


@router.get("/series/{series_id}/seasons/{number}")
def season(series_id: uuid.UUID, number: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not is_visible(db, "series", series_id):
        raise AppError(404, "NOT_FOUND", "Not found.")
    se = db.scalar(select(Season).where(Season.series_id == series_id, Season.season_number == number))
    if not se:
        raise AppError(404, "NOT_FOUND", "Not found.")
    eps = list(db.scalars(select(Episode).where(Episode.season_id == se.id).order_by(Episode.episode_number)))
    assets = deliverable_assets(db, user, "episode", [e.id for e in eps])
    return {"season_number": se.season_number, "episodes": [
        {"id": e.id, "episode_number": e.episode_number, "title": e.title, "air_date": e.air_date,
         "assets": assets.get(e.id, [])} for e in eps]}

import uuid
from typing import Literal
from fastapi import APIRouter, Depends, Query
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.api.deps import current_user
from app.catalog.service import KINDS, _localize, get_title
from app.core.db import get_db
from app.core.errors import AppError
from app.delivery import deliverable_assets
from app.publishing import is_visible, visible_clause
from app.models import CollectionMovie, Favorite, Movie, MovieCollection, Season, User

router = APIRouter()
Kind = Literal["movie", "series"]


def _404():
    return AppError(404, "NOT_FOUND", "Not found.")


@router.get("/movies/{movie_id}")
def movie(movie_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    t = get_title(db, "movie", movie_id, user.preferred_language)
    if not t:
        raise _404()
    t["favorited"] = db.get(Favorite, (user.id, "movie", movie_id)) is not None
    t["assets"] = deliverable_assets(db, user, "movie", [movie_id]).get(movie_id, [])
    return t


@router.get("/series/{series_id}")
def series(series_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    t = get_title(db, "series", series_id, user.preferred_language)
    if not t:
        raise _404()
    seasons = db.scalars(select(Season).where(Season.series_id == series_id).order_by(Season.season_number))
    t["favorited"] = db.get(Favorite, (user.id, "series", series_id)) is not None
    t["seasons"] = [{"season_number": s.season_number, "title": s.title} for s in seasons]
    return t


@router.get("/collections/{collection_id}")
def collection(collection_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = db.get(MovieCollection, collection_id)
    if not c:
        raise _404()
    rows = db.execute(select(Movie, CollectionMovie.sort_order).join(CollectionMovie, CollectionMovie.movie_id == Movie.id)
                      .where(CollectionMovie.collection_id == c.id, visible_clause("movie"))
                      .order_by(CollectionMovie.sort_order)).all()
    movies = [r[0] for r in rows]
    # Membership does not imply shared rights: only individually published movies are listed.
    return {"id": c.id, "name": c.name, "items": _localize(db, "movie", movies, user.preferred_language)}


@router.get("/me/favorites")
def list_favorites(cursor: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=50),
                   user: User = Depends(current_user), db: Session = Depends(get_db)):
    favs = list(db.scalars(select(Favorite).where(Favorite.user_id == user.id)
                           .order_by(Favorite.created_at.desc(), Favorite.content_id).offset(cursor).limit(limit + 1)))
    nxt = cursor + limit if len(favs) > limit else None
    favs = favs[:limit]
    loc = {}
    for kind in KINDS:
        rows = [db.get(KINDS[kind], f.content_id) for f in favs if f.content_kind == kind]
        rows = [r for r in rows if r and is_visible(db, kind, r.id)]
        for item in _localize(db, kind, rows, user.preferred_language):
            loc[(kind, item["id"])] = item
    items = [loc[(f.content_kind, f.content_id)] for f in favs if (f.content_kind, f.content_id) in loc]
    return {"items": items, "next_cursor": str(nxt) if nxt is not None else None}


@router.put("/me/favorites/{kind}/{item_id}")
def add_favorite(kind: Kind, item_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if get_title(db, kind, item_id, user.preferred_language) is None:
        raise _404()
    if db.get(Favorite, (user.id, kind, item_id)) is None:
        db.add(Favorite(user_id=user.id, content_kind=kind, content_id=item_id))
        try:
            db.commit()
        except IntegrityError:  # concurrent duplicate tap: already saved
            db.rollback()
    return {"favorited": True}


@router.delete("/me/favorites/{kind}/{item_id}")
def remove_favorite(kind: Kind, item_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.execute(delete(Favorite).where(Favorite.user_id == user.id, Favorite.content_kind == kind,
                                      Favorite.content_id == item_id))
    db.commit()
    return {"favorited": False}

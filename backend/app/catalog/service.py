from sqlalchemy import or_, select
from sqlalchemy.orm import Session
from app.models import LocalizedMetadata, Movie, TvSeries
from app.publishing import visible_clause

KINDS = {"movie": Movie, "series": TvSeries}


def _localize(db: Session, kind: str, rows, lang: str) -> list[dict]:
    """Bulk-load translations (no N+1). Missing translation -> original title, never invented (I18N-09)."""
    ids = [r.id for r in rows]
    tr = {}
    if ids:
        for m in db.scalars(select(LocalizedMetadata).where(
                LocalizedMetadata.content_kind == kind, LocalizedMetadata.content_id.in_(ids),
                LocalizedMetadata.language_code == lang)):
            tr[m.content_id] = m
    out = []
    for r in rows:
        m = tr.get(r.id)
        out.append({
            "id": r.id, "kind": kind,
            "title": m.title if m else r.original_title,
            "synopsis": m.synopsis if m else None,
            "title_language": lang if m else "original",
            "original_title": r.original_title,
            "year": getattr(r, "release_year", None),
        })
    return out


def list_titles(db: Session, kind: str, lang: str, q: str | None, offset: int, limit: int):
    model = KINDS[kind]
    stmt = select(model).where(visible_clause(kind))
    if q:
        like = f"%{q}%"
        translated = select(LocalizedMetadata.content_id).where(
            LocalizedMetadata.content_kind == kind, LocalizedMetadata.title.ilike(like))
        stmt = stmt.where(or_(model.original_title.ilike(like), model.id.in_(translated)))
    rows = list(db.scalars(stmt.order_by(model.created_at.desc(), model.id).offset(offset).limit(limit + 1)))
    nxt = offset + limit if len(rows) > limit else None
    return _localize(db, kind, rows[:limit], lang), nxt


def get_title(db: Session, kind: str, item_id, lang: str):
    model = KINDS[kind]
    r = db.scalar(select(model).where(model.id == item_id, visible_clause(kind)))
    if not r:
        return None
    return _localize(db, kind, [r], lang)[0]

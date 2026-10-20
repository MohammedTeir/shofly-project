"""Dev seed with fictional titles only (no real/licensed media). Usage: python -m scripts.seed"""
from app.core.db import Base, SessionLocal, engine
from app.fixtures import make_visible
from app.models import (CollectionMovie, Episode, LocalizedMetadata, Movie, MovieCollection, Season, TvSeries)

Base.metadata.create_all(engine)
with SessionLocal() as db:
    m = [Movie(original_title=f"Sample Film {i}", release_year=2020 + i, status="published") for i in (1, 2)]
    s = TvSeries(original_title="Sample Series", status="published")
    db.add_all(m + [s]); db.flush()
    c = MovieCollection(name="Sample Saga"); db.add(c); db.flush()
    for i, x in enumerate(m):
        db.add(CollectionMovie(collection_id=c.id, movie_id=x.id, sort_order=i))
    se = Season(series_id=s.id, season_number=1); db.add(se); db.flush()
    db.add_all([Episode(season_id=se.id, episode_number=n, title=f"Episode {n}") for n in (1, 2, 3)])
    db.commit(); make_visible(db, *m, s)  # fake verified assets + rights: DEV ONLY
    db.add(LocalizedMetadata(content_kind="movie", content_id=m[0].id, language_code="ar", title="فيلم تجريبي ١"))
    db.commit()
print("seeded")

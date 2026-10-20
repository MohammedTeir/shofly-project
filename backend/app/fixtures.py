"""Dev/test helper: make a title pass every visibility rule using clearly fake asset/rights rows. Never use in production."""
import uuid
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from app.models import ContentRight, Episode, MediaAsset, Movie, Season


def make_visible(db, *items):
    now = datetime.now(timezone.utc)
    for it in items:
        it.metadata_verified, it.status = True, "published"
        if isinstance(it, Movie):
            kind, tid, key = "movie", it.id, {"movie_id": it.id}
        else:
            ep = db.scalar(select(Episode).join(Season, Season.id == Episode.season_id).where(Season.series_id == it.id).limit(1))
            assert ep is not None, "series needs at least one episode"
            kind, tid, key = "episode", ep.id, {"episode_id": ep.id}
        db.add(MediaAsset(provider="fixture", provider_ref_encrypted="fixture", size_bytes=1,
                          checksum_sha256=uuid.uuid4().hex + uuid.uuid4().hex, upload_status="verified", **key))
        db.add(ContentRight(content_kind=kind, content_id=tid, license_type="fixture", proof_ref_encrypted="fixture",
                            telegram_allowed=True, territories=["ALL"], valid_from=now - timedelta(days=1),
                            valid_until=now + timedelta(days=365), review_status="APPROVED"))
    db.commit()

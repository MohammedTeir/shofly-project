import uuid
from datetime import date, datetime, timezone
from sqlalchemy import Boolean, CheckConstraint, BigInteger, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, JSON, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base


def now():
    return datetime.now(timezone.utc)


def pk():
    return mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = pk()
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(64))
    display_name: Mapped[str | None] = mapped_column(String(128))
    preferred_language: Mapped[str | None] = mapped_column(String(16))
    language_source: Mapped[str | None] = mapped_column(String(16))  # 'user' | 'telegram' | 'default'
    language_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    role: Mapped[str] = mapped_column(String(32), default="member")
    status: Mapped[str] = mapped_column(String(16), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class Movie(Base):
    __tablename__ = "movies"
    id: Mapped[uuid.UUID] = pk()
    tmdb_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    original_title: Mapped[str] = mapped_column(Text, index=True)
    original_language: Mapped[str | None] = mapped_column(String(16))
    release_year: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="draft")  # draft | published
    metadata_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class TvSeries(Base):
    __tablename__ = "tv_series"
    metadata_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    id: Mapped[uuid.UUID] = pk()
    tmdb_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    original_title: Mapped[str] = mapped_column(Text, index=True)
    original_language: Mapped[str | None] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Season(Base):
    __tablename__ = "seasons"
    __table_args__ = (UniqueConstraint("series_id", "season_number"),)
    id: Mapped[uuid.UUID] = pk()
    series_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tv_series.id"), index=True)
    season_number: Mapped[int] = mapped_column(Integer)  # 0 = specials
    title: Mapped[str | None] = mapped_column(Text)


class Episode(Base):
    __tablename__ = "episodes"
    __table_args__ = (UniqueConstraint("season_id", "episode_number"),)
    id: Mapped[uuid.UUID] = pk()
    season_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("seasons.id"), index=True)
    episode_number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str | None] = mapped_column(Text)
    air_date: Mapped[date | None] = mapped_column(Date)


class LocalizedMetadata(Base):
    __tablename__ = "localized_metadata"
    __table_args__ = (UniqueConstraint("content_kind", "content_id", "language_code"),)
    id: Mapped[uuid.UUID] = pk()
    content_kind: Mapped[str] = mapped_column(String(16))  # movie | series
    content_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    language_code: Mapped[str] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(Text)
    synopsis: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(32), default="manual")


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[uuid.UUID] = pk()
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    action: Mapped[str] = mapped_column(String(64))
    entity_kind: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    metadata_redacted: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class MovieCollection(Base):
    __tablename__ = "movie_collections"
    id: Mapped[uuid.UUID] = pk()
    tmdb_collection_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    name: Mapped[str] = mapped_column(Text)


class CollectionMovie(Base):
    __tablename__ = "collection_movies"
    collection_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("movie_collections.id"), primary_key=True)
    movie_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("movies.id"), primary_key=True)
    sort_order: Mapped[int] = mapped_column(Integer)


class Favorite(Base):
    __tablename__ = "favorites"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    content_kind: Mapped[str] = mapped_column(String(16), primary_key=True)
    content_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ImportJob(Base):
    __tablename__ = "import_jobs"
    id: Mapped[uuid.UUID] = pk()
    source_type: Mapped[str] = mapped_column(String(32))
    source_ref_encrypted: Mapped[str] = mapped_column(Text)
    requested_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(24), index=True)
    candidate_kind: Mapped[str | None] = mapped_column(String(16))  # movie | episode
    target_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    progress_percent: Mapped[int] = mapped_column(Integer, default=0)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    lease_epoch: Mapped[int] = mapped_column(Integer, default=0)  # compare-and-set guard for atomic claims
    lease_owner: Mapped[str | None] = mapped_column(String(64))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    idempotency_key: Mapped[str] = mapped_column(String(100), unique=True)
    error_code: Mapped[str | None] = mapped_column(String(40))
    error_message_safe: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class MediaAsset(Base):
    __tablename__ = "media_assets"
    __table_args__ = (
        CheckConstraint("(movie_id IS NOT NULL) <> (episode_id IS NOT NULL)", name="asset_exactly_one_target"),
        UniqueConstraint("movie_id", "checksum_sha256"), UniqueConstraint("episode_id", "checksum_sha256"),
    )
    id: Mapped[uuid.UUID] = pk()
    movie_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("movies.id"), index=True)
    episode_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("episodes.id"), index=True)
    import_job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("import_jobs.id"))
    provider: Mapped[str] = mapped_column(String(32))
    provider_ref_encrypted: Mapped[str] = mapped_column(Text)
    segment_refs_encrypted: Mapped[list | None] = mapped_column(JSON)  # ordered encrypted Telegram message references
    edition: Mapped[str | None] = mapped_column(String(32))
    quality: Mapped[str | None] = mapped_column(String(32))
    codec: Mapped[str | None] = mapped_column(String(32))
    audio_language: Mapped[str | None] = mapped_column(String(32))
    duration_sec: Mapped[int | None] = mapped_column(Integer)
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    checksum_sha256: Mapped[str] = mapped_column(String(64))
    upload_status: Mapped[str] = mapped_column(String(16), default="verified")
    visibility: Mapped[str] = mapped_column(String(16), default="private")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ContentRight(Base):
    __tablename__ = "content_rights"
    id: Mapped[uuid.UUID] = pk()
    content_kind: Mapped[str] = mapped_column(String(16))  # movie | episode (exact-target rights only)
    content_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    license_type: Mapped[str] = mapped_column(String(64))
    proof_ref_encrypted: Mapped[str] = mapped_column(Text)
    commercial_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    telegram_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    web_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    territories: Mapped[list | None] = mapped_column(JSON)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    review_status: Mapped[str] = mapped_column(String(16), default="PENDING")  # PENDING|APPROVED|REJECTED|REVOKED
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

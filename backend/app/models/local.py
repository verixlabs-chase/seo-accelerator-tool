import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LocalProfile(Base):
    __tablename__ = "local_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    campaign_id: Mapped[str] = mapped_column(String(36), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(80), nullable=False, default="gbp")
    profile_name: Mapped[str] = mapped_column(String(255), nullable=False)
    map_pack_position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class LocalHealthSnapshot(Base):
    __tablename__ = "local_health_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    campaign_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    profile_id: Mapped[str] = mapped_column(String(36), ForeignKey("local_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    health_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    details_json: Mapped[str] = mapped_column(Text, default="{}")
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True)


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    campaign_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    profile_id: Mapped[str] = mapped_column(String(36), ForeignKey("local_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    external_review_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    rating: Mapped[float] = mapped_column(Float, nullable=False)
    sentiment: Mapped[str] = mapped_column(String(20), nullable=False, default="neutral")
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True)


class ReviewVelocitySnapshot(Base):
    __tablename__ = "review_velocity_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    campaign_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    profile_id: Mapped[str] = mapped_column(String(36), ForeignKey("local_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    reviews_last_30d: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_rating_last_30d: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True)


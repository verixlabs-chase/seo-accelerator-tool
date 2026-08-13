import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Competitor(Base):
    __tablename__ = "competitors"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    campaign_id: Mapped[str] = mapped_column(String(36), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True)
    domain: Mapped[str] = mapped_column(String(320), nullable=False)
    label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    discovery_source: Mapped[str] = mapped_column(String(40), nullable=False, default="manual")
    review_status: Mapped[str] = mapped_column(String(24), nullable=False, default="confirmed", index=True)
    overlap_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    average_position: Mapped[float | None] = mapped_column(Float, nullable=True)
    estimated_traffic: Mapped[float | None] = mapped_column(Float, nullable=True)
    discovery_evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class CompetitorRanking(Base):
    __tablename__ = "competitor_rankings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    campaign_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    competitor_id: Mapped[str] = mapped_column(String(36), ForeignKey("competitors.id", ondelete="CASCADE"), nullable=False, index=True)
    keyword: Mapped[str] = mapped_column(String(255), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True)


class CompetitorPage(Base):
    __tablename__ = "competitor_pages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    campaign_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    competitor_id: Mapped[str] = mapped_column(String(36), ForeignKey("competitors.id", ondelete="CASCADE"), nullable=False, index=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    visibility_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True)


class CompetitorSignal(Base):
    __tablename__ = "competitor_signals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    campaign_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    competitor_id: Mapped[str] = mapped_column(String(36), ForeignKey("competitors.id", ondelete="CASCADE"), nullable=False, index=True)
    signal_key: Mapped[str] = mapped_column(String(120), nullable=False)
    signal_value: Mapped[str] = mapped_column(String(255), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True)

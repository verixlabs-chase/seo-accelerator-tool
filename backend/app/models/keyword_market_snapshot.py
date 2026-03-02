from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Float, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class KeywordMarketSnapshot(Base):
    __tablename__ = "keyword_market_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "keyword_id",
            "geo_scope",
            "device_class",
            "snapshot_date",
            name="uq_keyword_market_snapshots_keyword_geo_device_date",
        ),
        Index("ix_keyword_market_snapshots_keyword_id", "keyword_id"),
        Index("ix_keyword_market_snapshots_snapshot_date", "snapshot_date"),
        Index("ix_keyword_market_snapshots_geo_device_date", "geo_scope", "device_class", "snapshot_date"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    keyword_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("campaign_keywords.id", ondelete="CASCADE"),
        nullable=False,
    )
    search_volume: Mapped[int] = mapped_column(Integer, nullable=False)
    avg_cpc: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    geo_scope: Mapped[str] = mapped_column(String(64), nullable=False)
    device_class: Mapped[str] = mapped_column(String(16), nullable=False)
    source_provider: Mapped[str] = mapped_column(String(64), nullable=False)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False)
    deterministic_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

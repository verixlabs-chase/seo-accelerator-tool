from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class KeywordDailyEconomics(Base):
    __tablename__ = "keyword_daily_economics"
    __table_args__ = (
        UniqueConstraint("keyword_id", "metric_date", name="uq_keyword_daily_economics_keyword_date"),
        Index("ix_keyword_daily_economics_campaign_id", "campaign_id"),
        Index("ix_keyword_daily_economics_keyword_id", "keyword_id"),
        Index("ix_keyword_daily_economics_metric_date", "metric_date"),
        Index("ix_keyword_daily_economics_keyword_date", "keyword_id", "metric_date"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    campaign_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("campaigns.id", ondelete="CASCADE"),
        nullable=False,
    )
    keyword_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("campaign_keywords.id", ondelete="CASCADE"),
        nullable=False,
    )
    metric_date: Mapped[date] = mapped_column(Date, nullable=False)
    search_volume: Mapped[int] = mapped_column(Integer, nullable=False)
    cpc: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    estimated_clicks: Mapped[int] = mapped_column(Integer, nullable=False)
    paid_equivalent_value: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    ctr_model_version: Mapped[str] = mapped_column(String(32), nullable=False)
    deterministic_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

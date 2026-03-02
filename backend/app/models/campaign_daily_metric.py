from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Float, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CampaignDailyMetric(Base):
    __tablename__ = 'campaign_daily_metrics'
    __table_args__ = (
        UniqueConstraint('campaign_id', 'metric_date', name='uq_campaign_daily_metrics_campaign_date'),
        Index('ix_campaign_daily_metrics_organization_id', 'organization_id'),
        Index('ix_campaign_daily_metrics_portfolio_id', 'portfolio_id'),
        Index('ix_campaign_daily_metrics_campaign_id', 'campaign_id'),
        Index('ix_campaign_daily_metrics_metric_date', 'metric_date'),
        Index('ix_campaign_daily_metrics_campaign_date', 'campaign_id', 'metric_date'),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey('organizations.id', ondelete='CASCADE'),
        nullable=False,
    )
    portfolio_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey('portfolios.id', ondelete='SET NULL'),
        nullable=True,
    )
    sub_account_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey('sub_accounts.id', ondelete='SET NULL'),
        nullable=True,
    )
    campaign_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey('campaigns.id', ondelete='CASCADE'),
        nullable=False,
    )
    metric_date: Mapped[date] = mapped_column(Date, nullable=False)
    clicks: Mapped[int | None] = mapped_column(Integer, nullable=True)
    impressions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    avg_position: Mapped[float | None] = mapped_column(Float, nullable=True)
    sessions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    conversions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    technical_issue_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    intelligence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    reviews_last_30d: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_rating_last_30d: Mapped[float | None] = mapped_column(Float, nullable=True)
    cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    revenue: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    normalization_version: Mapped[str] = mapped_column(String(32), nullable=False, default='analytics-v1')
    deterministic_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AnalyticsDailyMetric(Base):
    __tablename__ = 'analytics_daily_metrics'
    __table_args__ = (
        UniqueConstraint('campaign_id', 'metric_date', name='uq_analytics_daily_metrics_campaign_date'),
        Index('ix_analytics_daily_metrics_organization_id', 'organization_id'),
        Index('ix_analytics_daily_metrics_campaign_id', 'campaign_id'),
        Index('ix_analytics_daily_metrics_metric_date', 'metric_date'),
        Index('ix_analytics_daily_metrics_campaign_date', 'campaign_id', 'metric_date'),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey('organizations.id', ondelete='CASCADE'),
        nullable=False,
    )
    campaign_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey('campaigns.id', ondelete='CASCADE'),
        nullable=False,
    )
    metric_date: Mapped[date] = mapped_column(Date, nullable=False)
    sessions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    conversions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deterministic_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Index, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SearchConsoleDailyMetric(Base):
    __tablename__ = 'search_console_daily_metrics'
    __table_args__ = (
        UniqueConstraint('campaign_id', 'metric_date', name='uq_search_console_daily_metrics_campaign_date'),
        Index('ix_search_console_daily_metrics_organization_id', 'organization_id'),
        Index('ix_search_console_daily_metrics_campaign_id', 'campaign_id'),
        Index('ix_search_console_daily_metrics_metric_date', 'metric_date'),
        Index('ix_search_console_daily_metrics_campaign_date', 'campaign_id', 'metric_date'),
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
    clicks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    impressions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ctr: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_position: Mapped[float | None] = mapped_column(Float, nullable=True)
    property_uri: Mapped[str] = mapped_column(String(500), nullable=False, default="unknown")
    search_type: Mapped[str] = mapped_column(String(40), nullable=False, default="web")
    dimensions: Mapped[list] = mapped_column(JSON, nullable=False, default=lambda: ["date"])
    filters: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    metric_contract_versions: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    scope_key: Mapped[str] = mapped_column(String(64), nullable=False, default="legacy")
    deterministic_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

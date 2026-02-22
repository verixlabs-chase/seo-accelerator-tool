from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PortfolioUsageDaily(Base):
    __tablename__ = "portfolio_usage_daily"
    __table_args__ = (
        UniqueConstraint("portfolio_id", "usage_date", name="uq_portfolio_usage_daily_portfolio_date"),
        Index("ix_portfolio_usage_daily_portfolio_date", "portfolio_id", "usage_date"),
        Index("ix_portfolio_usage_daily_org_usage_date", "organization_id", "usage_date"),
        CheckConstraint("provider_calls >= 0", name="ck_portfolio_usage_daily_provider_calls_non_negative"),
        CheckConstraint("crawl_pages_fetched >= 0", name="ck_portfolio_usage_daily_crawl_pages_non_negative"),
        CheckConstraint("reports_generated >= 0", name="ck_portfolio_usage_daily_reports_non_negative"),
        CheckConstraint("active_campaign_days >= 0", name="ck_portfolio_usage_daily_active_campaign_days_non_negative"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    portfolio_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    usage_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    provider_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    crawl_pages_fetched: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reports_generated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active_campaign_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

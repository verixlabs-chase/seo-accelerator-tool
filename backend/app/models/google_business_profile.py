from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class GoogleBusinessProfileSnapshot(Base):
    __tablename__ = "google_business_profile_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "connection_id",
            "profile_hash",
            name="uq_gbp_snapshots_connection_hash",
        ),
        Index(
            "ix_gbp_snapshots_campaign_captured",
            "campaign_id",
            "captured_at",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    connection_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("data_connections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    campaign_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    business_location_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("business_locations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    external_resource_id: Mapped[str] = mapped_column(String(120), nullable=False)
    profile_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    profile_data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    audit_summary: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), index=True
    )


class GoogleBusinessProfileDailyMetric(Base):
    __tablename__ = "google_business_profile_daily_metrics"
    __table_args__ = (
        UniqueConstraint(
            "connection_id",
            "metric_date",
            "metric_name",
            name="uq_gbp_daily_metrics_connection_date_metric",
        ),
        Index(
            "ix_gbp_daily_metrics_campaign_date",
            "campaign_id",
            "metric_date",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    connection_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("data_connections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    campaign_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    business_location_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("business_locations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    metric_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    metric_name: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    metric_value: Mapped[int | None] = mapped_column(Integer, nullable=True)
    missing_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_name: Mapped[str] = mapped_column(
        String(64), nullable=False, default="google_business_profile"
    )
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )


class GoogleBusinessProfileSearchKeyword(Base):
    __tablename__ = "google_business_profile_search_keywords"
    __table_args__ = (
        UniqueConstraint(
            "connection_id",
            "metric_month",
            "keyword",
            name="uq_gbp_search_keywords_connection_month_keyword",
        ),
        Index(
            "ix_gbp_search_keywords_campaign_month",
            "campaign_id",
            "metric_month",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    connection_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("data_connections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    campaign_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    business_location_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("business_locations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    metric_month: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    keyword: Mapped[str] = mapped_column(String(500), nullable=False)
    impressions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_name: Mapped[str] = mapped_column(
        String(64), nullable=False, default="google_business_profile"
    )
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

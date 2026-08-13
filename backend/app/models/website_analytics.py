from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AnalyticsLandingPageDailyMetric(Base):
    __tablename__ = "analytics_landing_page_daily_metrics"
    __table_args__ = (
        UniqueConstraint(
            "campaign_id",
            "metric_date",
            "dimension_hash",
            name="uq_analytics_landing_page_campaign_date_hash",
        ),
        Index(
            "ix_analytics_landing_page_campaign_date",
            "campaign_id",
            "metric_date",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    tenant_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    business_location_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("business_locations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    campaign_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("campaigns.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    metric_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    landing_page: Mapped[str] = mapped_column(Text, nullable=False)
    dimension_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    sessions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    engaged_sessions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    key_events: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
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


class AnalyticsTrafficSourceDailyMetric(Base):
    __tablename__ = "analytics_traffic_source_daily_metrics"
    __table_args__ = (
        UniqueConstraint(
            "campaign_id",
            "metric_date",
            "dimension_hash",
            name="uq_analytics_traffic_source_campaign_date_hash",
        ),
        Index(
            "ix_analytics_traffic_source_campaign_date",
            "campaign_id",
            "metric_date",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    tenant_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    business_location_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("business_locations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    campaign_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("campaigns.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    metric_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    source_medium: Mapped[str] = mapped_column(String(500), nullable=False)
    dimension_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    sessions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    engaged_sessions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    key_events: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
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


class WebsiteFormEvent(Base):
    __tablename__ = "website_form_events"
    __table_args__ = (
        UniqueConstraint(
            "data_connection_id",
            "event_id",
            name="uq_website_form_events_connection_event",
        ),
        Index(
            "ix_website_form_events_campaign_occurred",
            "campaign_id",
            "occurred_at",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    tenant_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    business_location_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("business_locations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    campaign_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("campaigns.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    data_connection_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("data_connections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_id: Mapped[str] = mapped_column(String(128), nullable=False)
    event_name: Mapped[str] = mapped_column(String(40), nullable=False)
    website: Mapped[str] = mapped_column(String(500), nullable=False)
    page_url: Mapped[str] = mapped_column(Text, nullable=False)
    form_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

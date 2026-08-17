from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UrlInspectionSnapshot(Base):
    __tablename__ = "url_inspection_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "campaign_id",
            "inspection_url",
            name="uq_url_inspection_snapshots_campaign_url",
        ),
        Index(
            "ix_url_inspection_snapshots_campaign_inspected",
            "campaign_id",
            "inspected_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    campaign_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    connection_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("data_connections.id", ondelete="CASCADE"), nullable=False, index=True
    )
    page_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("pages.id", ondelete="SET NULL"), nullable=True, index=True
    )
    site_url: Mapped[str] = mapped_column(Text, nullable=False)
    inspection_url: Mapped[str] = mapped_column(Text, nullable=False)
    verdict: Mapped[str] = mapped_column(String(40), nullable=False, default="VERDICT_UNSPECIFIED")
    coverage_state: Mapped[str | None] = mapped_column(String(240), nullable=True)
    robots_txt_state: Mapped[str | None] = mapped_column(String(60), nullable=True)
    indexing_state: Mapped[str | None] = mapped_column(String(60), nullable=True)
    page_fetch_state: Mapped[str | None] = mapped_column(String(80), nullable=True)
    google_canonical: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_canonical: Mapped[str | None] = mapped_column(Text, nullable=True)
    crawled_as: Mapped[str | None] = mapped_column(String(60), nullable=True)
    last_crawl_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sitemap_urls: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    referring_urls: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    source_contract_version: Mapped[str] = mapped_column(
        String(60), nullable=False, default="google-url-inspection-v1"
    )
    inspected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )


class SearchConsoleSitemapSnapshot(Base):
    __tablename__ = "search_console_sitemap_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "campaign_id",
            "sitemap_url",
            name="uq_search_console_sitemaps_campaign_url",
        ),
        Index(
            "ix_search_console_sitemaps_campaign_observed",
            "campaign_id",
            "observed_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    campaign_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    connection_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("data_connections.id", ondelete="CASCADE"), nullable=False, index=True
    )
    site_url: Mapped[str] = mapped_column(Text, nullable=False)
    sitemap_url: Mapped[str] = mapped_column(Text, nullable=False)
    sitemap_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    is_pending: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_sitemaps_index: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    warnings: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    errors: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    submitted_url_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    contents: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    last_submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_downloaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_contract_version: Mapped[str] = mapped_column(
        String(60), nullable=False, default="google-sitemaps-v3"
    )
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Page(Base):
    __tablename__ = "pages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    campaign_id: Mapped[str] = mapped_column(String(36), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    last_crawled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class CrawlRun(Base):
    __tablename__ = "crawl_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    campaign_id: Mapped[str] = mapped_column(String(36), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True)
    crawl_type: Mapped[str] = mapped_column(String(20), nullable=False, default="deep")
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="scheduled")
    seed_url: Mapped[str] = mapped_column(Text, nullable=False)
    pages_discovered: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CrawlPageResult(Base):
    __tablename__ = "crawl_page_results"
    __table_args__ = (Index("ix_crawl_page_results_tenant_campaign_crawled", "tenant_id", "campaign_id", "crawled_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    campaign_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    crawl_run_id: Mapped[str] = mapped_column(String(36), ForeignKey("crawl_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    page_id: Mapped[str] = mapped_column(String(36), ForeignKey("pages.id", ondelete="CASCADE"), nullable=False)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_indexable: Mapped[int] = mapped_column(Integer, default=1)
    title: Mapped[str | None] = mapped_column(String(320), nullable=True)
    meta_description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    heading_text: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    body_text_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    redirect_chain: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    redirect_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    canonical_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    word_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    internal_link_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    structured_data_types: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    structured_data_valid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    crawled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True)


class TechnicalIssue(Base):
    __tablename__ = "technical_issues"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    campaign_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    crawl_run_id: Mapped[str] = mapped_column(String(36), ForeignKey("crawl_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    page_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("pages.id", ondelete="SET NULL"), nullable=True)
    issue_code: Mapped[str] = mapped_column(String(120), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="medium")
    details_json: Mapped[str] = mapped_column(Text, default="{}")
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True)


class CrawlFrontierUrl(Base):
    __tablename__ = "crawl_frontier_urls"
    __table_args__ = (
        UniqueConstraint("crawl_run_id", "normalized_url", name="uq_crawl_frontier_run_normalized_url"),
        Index("ix_crawl_frontier_urls_run_status_created", "crawl_run_id", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    campaign_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    crawl_run_id: Mapped[str] = mapped_column(String(36), ForeignKey("crawl_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_url: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    depth: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    discovered_from_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class CrawlInternalLink(Base):
    __tablename__ = "crawl_internal_links"
    __table_args__ = (
        UniqueConstraint(
            "crawl_run_id",
            "source_page_id",
            "normalized_target_url",
            name="uq_crawl_links_run_source_target",
        ),
        Index(
            "ix_crawl_links_run_target",
            "crawl_run_id",
            "normalized_target_url",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    campaign_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    crawl_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("crawl_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_page_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("pages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_page_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("pages.id", ondelete="SET NULL"), nullable=True, index=True
    )
    target_url: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_target_url: Mapped[str] = mapped_column(Text, nullable=False)
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

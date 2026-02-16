import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
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

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    campaign_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    crawl_run_id: Mapped[str] = mapped_column(String(36), ForeignKey("crawl_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    page_id: Mapped[str] = mapped_column(String(36), ForeignKey("pages.id", ondelete="CASCADE"), nullable=False)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_indexable: Mapped[int] = mapped_column(Integer, default=1)
    title: Mapped[str | None] = mapped_column(String(320), nullable=True)
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


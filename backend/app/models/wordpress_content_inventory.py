import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WordPressContentSyncRun(Base):
    __tablename__ = "wordpress_content_sync_runs"
    __table_args__ = (
        CheckConstraint(
            "status in ('running','complete','failed')",
            name="ck_wordpress_content_sync_runs_status",
        ),
        Index(
            "ix_wordpress_content_sync_runs_campaign_started",
            "campaign_id",
            "started_at",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    campaign_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    wordpress_site_connection_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("wordpress_site_connections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running", index=True)
    item_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_total_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    truncated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    plugin_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    wordpress_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    php_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    seo_plugins: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WordPressContentItem(Base):
    __tablename__ = "wordpress_content_items"
    __table_args__ = (
        UniqueConstraint(
            "sync_run_id",
            "wp_post_id",
            name="uq_wordpress_content_items_run_post",
        ),
        Index(
            "ix_wordpress_content_items_campaign_url",
            "campaign_id",
            "url",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    campaign_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sync_run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("wordpress_content_sync_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    wp_post_id: Mapped[int] = mapped_column(Integer, nullable=False)
    post_type: Mapped[str] = mapped_column(String(80), nullable=False)
    publication_status: Mapped[str] = mapped_column(String(24), nullable=False)
    slug: Mapped[str] = mapped_column(String(320), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    meta_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    meta_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    canonical_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    headings: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    internal_links: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    schema_types: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    schema_present: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    word_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    revision_id: Mapped[str] = mapped_column(String(120), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    modified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

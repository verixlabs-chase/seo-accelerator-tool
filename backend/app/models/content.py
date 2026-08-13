import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    DateTime,
    Float,
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


class ContentAsset(Base):
    __tablename__ = "content_assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    campaign_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    cluster_name: Mapped[str] = mapped_column(String(120), nullable=False)
    title: Mapped[str] = mapped_column(String(320), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="planned")
    target_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    planned_month: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class ContentBrief(Base):
    __tablename__ = "content_briefs"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "idempotency_key",
            name="uq_content_briefs_tenant_idempotency",
        ),
        Index("ix_content_briefs_campaign_created", "campaign_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    campaign_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    business_location_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("business_locations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    suggestion_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("keyword_research_suggestions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    competitor_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("competitors.id", ondelete="CASCADE"), nullable=False, index=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft")
    title: Mapped[str] = mapped_column(String(320), nullable=False)
    primary_keyword: Mapped[str] = mapped_column(String(255), nullable=False)
    recommended_page_action: Mapped[str] = mapped_column(String(40), nullable=False)
    target_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    competitor_domain: Mapped[str] = mapped_column(String(320), nullable=False)
    competitor_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    service_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    service_area_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    evidence: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    outline: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )


class EditorialCalendar(Base):
    __tablename__ = "editorial_calendar"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    campaign_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    content_asset_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("content_assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    month_number: Mapped[int] = mapped_column(Integer, nullable=False)
    planned_publish_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class InternalLinkMap(Base):
    __tablename__ = "internal_link_map"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    campaign_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    source_asset_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("content_assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_asset_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("content_assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    anchor_text: Mapped[str] = mapped_column(String(255), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.75)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )


class ContentQcEvent(Base):
    __tablename__ = "content_qc_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    campaign_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    content_asset_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("content_assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    check_name: Mapped[str] = mapped_column(String(120), nullable=False)
    passed: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    score: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    details_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )

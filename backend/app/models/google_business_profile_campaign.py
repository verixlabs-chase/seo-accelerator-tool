from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class GoogleBusinessProfileCampaign(Base):
    """Approval snapshot for one typed action across an immutable location set."""

    __tablename__ = "google_business_profile_campaigns"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "request_key",
            name="uq_gbp_campaigns_org_request_key",
        ),
        Index(
            "ix_gbp_campaigns_org_created",
            "organization_id",
            "created_at",
        ),
        Index(
            "ix_gbp_campaigns_org_status",
            "organization_id",
            "status",
        ),
        CheckConstraint(
            "action_type in ('local_post','photo_upload')",
            name="ck_gbp_campaigns_action_type",
        ),
        CheckConstraint(
            "status in ('draft','awaiting_approval','blocked','approved_hold','cancelled')",
            name="ck_gbp_campaigns_status",
        ),
        CheckConstraint("version >= 1", name="ck_gbp_campaigns_version"),
        CheckConstraint(
            "ready_count >= 0 and blocked_count >= 0",
            name="ck_gbp_campaigns_nonnegative_counts",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
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
    target_snapshot_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("portfolio_target_snapshots.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    action_type: Mapped[str] = mapped_column(String(32), nullable=False)
    request_key: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    payload_template_json: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False, default=dict
    )
    target_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    approval_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    preflight_json: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False, default=dict
    )
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ready_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    blocked_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class GoogleBusinessProfileCampaignVariant(Base):
    """Frozen rendered payload and preflight result for one authorized profile."""

    __tablename__ = "google_business_profile_campaign_variants"
    __table_args__ = (
        UniqueConstraint(
            "profile_campaign_id",
            "business_location_id",
            name="uq_gbp_campaign_variants_campaign_location",
        ),
        Index(
            "ix_gbp_campaign_variants_campaign_status",
            "profile_campaign_id",
            "status",
        ),
        CheckConstraint(
            "status in ('ready','blocked')",
            name="ck_gbp_campaign_variants_status",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
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
    profile_campaign_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("google_business_profile_campaigns.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    business_location_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("business_locations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    campaign_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True, index=True
    )
    connection_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("data_connections.id", ondelete="SET NULL"), nullable=True, index=True
    )
    external_resource_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    location_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="blocked")
    rendered_payload_json: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False, default=dict
    )
    checks_json: Mapped[list] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False, default=list
    )
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    reason_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reason_message: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

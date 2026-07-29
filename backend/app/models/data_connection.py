from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DataConnection(Base):
    __tablename__ = "data_connections"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "provider_name",
            "campaign_id",
            name="uq_data_connections_org_provider_campaign",
        ),
        Index(
            "ix_data_connections_due_sync",
            "status",
            "next_sync_at",
        ),
        Index(
            "ix_data_connections_org_provider",
            "organization_id",
            "provider_name",
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
    provider_name: Mapped[str] = mapped_column(String(80), nullable=False)
    external_resource_id: Mapped[str] = mapped_column(String(500), nullable=False)
    external_resource_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    resource_scope: Mapped[str] = mapped_column(String(40), nullable=False, default="property")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="connected", index=True)
    last_sync_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sync_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    sync_cursor: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    connection_metadata: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_by_user_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
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

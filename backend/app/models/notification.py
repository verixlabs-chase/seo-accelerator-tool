from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Notification(Base):
    """Immutable in-product notice materialized from an approved product event."""

    __tablename__ = "notifications"
    __table_args__ = (
        CheckConstraint("tenant_id = organization_id", name="ck_notifications_scope"),
        CheckConstraint(
            "event_type in ('report.ready','action.failed')",
            name="ck_notifications_event_type",
        ),
        CheckConstraint(
            "severity in ('information','needs_attention')",
            name="ck_notifications_severity",
        ),
        CheckConstraint(
            "length(semantic_fingerprint) = 64",
            name="ck_notifications_semantic_fingerprint",
        ),
        CheckConstraint(
            "cooldown_expires_at > cooldown_window_started_at",
            name="ck_notifications_cooldown_window",
        ),
        CheckConstraint(
            "action_url like '/%' and action_url not like '//%'",
            name="ck_notifications_action_url",
        ),
        ForeignKeyConstraint(
            ["location_id", "organization_id"],
            ["business_locations.id", "business_locations.organization_id"],
            ondelete="RESTRICT",
            name="fk_notifications_location_org",
        ),
        UniqueConstraint(
            "id",
            "tenant_id",
            "organization_id",
            name="uq_notifications_scoped_identity",
        ),
        UniqueConstraint(
            "tenant_id",
            "source_event_id",
            name="uq_notifications_source_event",
        ),
        UniqueConstraint(
            "tenant_id",
            "semantic_fingerprint",
            "cooldown_window_started_at",
            name="uq_notifications_semantic_cooldown",
        ),
        Index(
            "ix_notifications_org_observed",
            "organization_id",
            "observed_at",
        ),
        Index(
            "ix_notifications_org_location_observed",
            "organization_id",
            "location_id",
            "observed_at",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    schema_version: Mapped[str] = mapped_column(
        String(40), nullable=False, default="alt1-notification-v1"
    )
    tenant_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    location_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    organization_name: Mapped[str] = mapped_column(String(255), nullable=False)
    location_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    source_event_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("event_outbox.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    source_event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    source_label: Mapped[str] = mapped_column(String(80), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(40), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    meaning: Mapped[str] = mapped_column(Text, nullable=False)
    action_label: Mapped[str] = mapped_column(String(120), nullable=False)
    action_url: Mapped[str] = mapped_column(String(500), nullable=False)
    freshness_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    semantic_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    cooldown_window_started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    cooldown_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )


class NotificationUserState(Base):
    """Per-member durable read and dismissal state for one notification."""

    __tablename__ = "notification_user_states"
    __table_args__ = (
        CheckConstraint(
            "tenant_id = organization_id",
            name="ck_notification_user_states_scope",
        ),
        CheckConstraint(
            "read_at is not null or dismissed_at is not null",
            name="ck_notification_user_states_has_state",
        ),
        ForeignKeyConstraint(
            ["notification_id", "tenant_id", "organization_id"],
            ["notifications.id", "notifications.tenant_id", "notifications.organization_id"],
            ondelete="CASCADE",
            name="fk_notification_user_states_notification_scope",
        ),
        UniqueConstraint(
            "notification_id",
            "user_id",
            name="uq_notification_user_states_notification_user",
        ),
        Index(
            "ix_notification_user_states_user_state",
            "organization_id",
            "user_id",
            "dismissed_at",
            "read_at",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    tenant_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    notification_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dismissed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

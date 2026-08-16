from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AutomationWebhookConnection(Base):
    __tablename__ = "automation_webhook_connections"
    __table_args__ = (
        CheckConstraint(
            "provider in ('zapier','make','pipedream')",
            name="ck_automation_webhook_connections_provider",
        ),
        CheckConstraint(
            "status in ('pending','active','unhealthy','paused','disconnected')",
            name="ck_automation_webhook_connections_status",
        ),
        CheckConstraint(
            "verification_status in ('not_tested','verified','failed')",
            name="ck_automation_webhook_connections_verification",
        ),
        CheckConstraint(
            "signing_secret_version >= 1 AND consecutive_failures >= 0",
            name="ck_automation_webhook_connections_counters",
        ),
        UniqueConstraint(
            "tenant_id",
            "organization_id",
            "name",
            name="uq_automation_webhook_connections_scope_name",
        ),
        UniqueConstraint(
            "id",
            "tenant_id",
            "organization_id",
            name="uq_automation_webhook_connections_id_scope",
        ),
        Index(
            "ix_automation_webhook_connections_scope_status",
            "tenant_id",
            "organization_id",
            "status",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    endpoint_host: Mapped[str] = mapped_column(String(253), nullable=False)
    event_types_json: Mapped[str] = mapped_column(Text, nullable=False)
    encrypted_config_blob: Mapped[str | None] = mapped_column(Text, nullable=True)
    key_reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    key_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    signing_secret_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    verification_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="not_tested"
    )
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL")
    )
    disconnected_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL")
    )
    paused_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL")
    )
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    disconnected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )


class AutomationWebhookDelivery(Base):
    __tablename__ = "automation_webhook_deliveries"
    __table_args__ = (
        CheckConstraint(
            "status in ('pending','delivered','failed','dead_letter','cancelled')",
            name="ck_automation_webhook_deliveries_status",
        ),
        CheckConstraint(
            "attempt_count >= 0 AND attempt_count <= max_attempts AND max_attempts >= 3",
            name="ck_automation_webhook_deliveries_attempts",
        ),
        CheckConstraint(
            "delivery_kind in ('test','product') AND recovery_count >= 0",
            name="ck_automation_webhook_deliveries_kind_recovery",
        ),
        ForeignKeyConstraint(
            ["connection_id", "tenant_id", "organization_id"],
            [
                "automation_webhook_connections.id",
                "automation_webhook_connections.tenant_id",
                "automation_webhook_connections.organization_id",
            ],
            name="fk_automation_webhook_deliveries_connection_scope",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "connection_id",
            "event_id",
            name="uq_automation_webhook_deliveries_connection_event",
        ),
        UniqueConstraint(
            "id",
            "tenant_id",
            "organization_id",
            name="uq_automation_webhook_deliveries_id_scope",
        ),
        Index(
            "ix_automation_webhook_deliveries_connection_created",
            "connection_id",
            "created_at",
        ),
        Index(
            "ix_automation_webhook_deliveries_scope_status",
            "tenant_id",
            "organization_id",
            "status",
        ),
        Index(
            "ix_automation_webhook_deliveries_platform_job",
            "platform_job_id",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    connection_id: Mapped[str] = mapped_column(String(36), nullable=False)
    event_id: Mapped[str] = mapped_column(String(80), nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    delivery_kind: Mapped[str] = mapped_column(
        String(20), nullable=False, default="test"
    )
    source_outbox_event_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("event_outbox.id", ondelete="RESTRICT")
    )
    platform_job_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("platform_jobs.id", ondelete="SET NULL")
    )
    encrypted_event_blob: Mapped[str] = mapped_column(Text, nullable=False)
    event_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    recovery_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_reason_code: Mapped[str | None] = mapped_column(String(80))
    last_response_status: Mapped[int | None] = mapped_column(Integer)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dead_lettered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )


class AutomationWebhookDeliveryAttempt(Base):
    __tablename__ = "automation_webhook_delivery_attempts"
    __table_args__ = (
        CheckConstraint(
            "status in ('delivered','failed')",
            name="ck_automation_webhook_delivery_attempts_status",
        ),
        CheckConstraint(
            "attempt_number >= 1 AND duration_ms >= 0",
            name="ck_automation_webhook_delivery_attempts_counters",
        ),
        ForeignKeyConstraint(
            ["delivery_id", "tenant_id", "organization_id"],
            [
                "automation_webhook_deliveries.id",
                "automation_webhook_deliveries.tenant_id",
                "automation_webhook_deliveries.organization_id",
            ],
            name="fk_automation_webhook_delivery_attempts_delivery_scope",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "delivery_id",
            "attempt_number",
            name="uq_automation_webhook_delivery_attempts_number",
        ),
        Index(
            "ix_automation_webhook_delivery_attempts_delivery",
            "delivery_id",
            "attempted_at",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    delivery_id: Mapped[str] = mapped_column(String(36), nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    response_status: Mapped[int | None] = mapped_column(Integer)
    reason_code: Mapped[str | None] = mapped_column(String(80))
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

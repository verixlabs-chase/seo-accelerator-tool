from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    JSON,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class GovernedAIProviderRoutingReadiness(Base):
    """Append-only proof that a standby candidate still has a safe fallback."""

    __tablename__ = "governed_ai_provider_routing_readiness"
    __table_args__ = (
        CheckConstraint(
            "status in ('passed','blocked')",
            name="ck_ai_provider_readiness_status",
        ),
        CheckConstraint(
            "managed_backend = 'mistral' AND "
            "managed_route_status in ('healthy','stale','unavailable','not_configured')",
            name="ck_ai_provider_readiness_managed",
        ),
        CheckConstraint(
            "traffic_percentage = 0 AND routing_enabled = false AND "
            "customer_prompts_allowed = false AND automatic_changes_allowed = false "
            "AND automatic_activation_allowed = false AND candidate_run_count = 0",
            name="ck_ai_provider_readiness_no_routing",
        ),
        CheckConstraint(
            "usage_window_days = 30 AND managed_run_count >= 0 AND "
            "managed_validated_count >= 0 AND managed_fallback_count >= 0 AND "
            "managed_input_tokens >= 0 AND managed_output_tokens >= 0",
            name="ck_ai_provider_readiness_usage",
        ),
        CheckConstraint(
            "status != 'passed' OR (managed_route_status = 'healthy' AND "
            "standby_evidence_current = true AND rollback_ready = true)",
            name="ck_ai_provider_readiness_passed",
        ),
        ForeignKeyConstraint(
            ["connection_id", "tenant_id", "organization_id"],
            [
                "governed_ai_provider_connections.id",
                "governed_ai_provider_connections.tenant_id",
                "governed_ai_provider_connections.organization_id",
            ],
            ondelete="RESTRICT",
            name="fk_ai_provider_readiness_connection_scope",
        ),
        ForeignKeyConstraint(
            ["standby_event_id", "tenant_id", "organization_id", "connection_id"],
            [
                "governed_ai_provider_standby_events.id",
                "governed_ai_provider_standby_events.tenant_id",
                "governed_ai_provider_standby_events.organization_id",
                "governed_ai_provider_standby_events.connection_id",
            ],
            ondelete="RESTRICT",
            name="fk_ai_provider_readiness_standby_scope",
        ),
        UniqueConstraint(
            "tenant_id",
            "organization_id",
            "connection_id",
            "idempotency_key",
            name="uq_ai_provider_readiness_idempotency",
        ),
        UniqueConstraint(
            "id",
            "tenant_id",
            "organization_id",
            "connection_id",
            name="uq_ai_provider_routing_readiness_id_scope",
        ),
        Index(
            "ix_ai_provider_readiness_connection_created",
            "connection_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    connection_id: Mapped[str] = mapped_column(String(36), nullable=False)
    standby_event_id: Mapped[str] = mapped_column(String(36), nullable=False)
    readiness_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    managed_backend: Mapped[str] = mapped_column(
        String(32), nullable=False, default="mistral"
    )
    managed_route_status: Mapped[str] = mapped_column(String(24), nullable=False)
    managed_evidence_hash: Mapped[str | None] = mapped_column(String(64))
    managed_evidence_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    standby_evidence_current: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    rollback_ready: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    blockers: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    usage_window_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    managed_run_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    managed_validated_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    managed_fallback_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    managed_input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    managed_output_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    candidate_run_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    traffic_percentage: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    routing_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    customer_prompts_allowed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    automatic_changes_allowed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    automatic_activation_allowed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    artifact_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

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


class GovernedAIProviderCanaryEvent(Base):
    """Append-only owner or safety-system decision for a fixed private-AI canary."""

    __tablename__ = "governed_ai_provider_canary_events"
    __table_args__ = (
        CheckConstraint(
            "action in ('enabled','disabled','automatic_rollback')",
            name="ck_ai_provider_canary_event_action",
        ),
        CheckConstraint(
            "feature = 'intelligence_brief' AND max_prompts_per_day = 1",
            name="ck_ai_provider_canary_event_scope",
        ),
        CheckConstraint(
            "automatic_activation_allowed = false AND automatic_changes_allowed = false",
            name="ck_ai_provider_canary_event_no_authority",
        ),
        CheckConstraint(
            "(action = 'enabled' AND state = 'canary' AND traffic_percentage = 5 "
            "AND customer_prompts_allowed = true AND automatic_rollback_enabled = true) "
            "OR (action != 'enabled' AND state = 'inactive' AND traffic_percentage = 0 "
            "AND customer_prompts_allowed = false)",
            name="ck_ai_provider_canary_event_state",
        ),
        ForeignKeyConstraint(
            ["connection_id", "tenant_id", "organization_id"],
            [
                "governed_ai_provider_connections.id",
                "governed_ai_provider_connections.tenant_id",
                "governed_ai_provider_connections.organization_id",
            ],
            ondelete="RESTRICT",
            name="fk_ai_provider_canary_connection_scope",
        ),
        ForeignKeyConstraint(
            ["readiness_id", "tenant_id", "organization_id", "connection_id"],
            [
                "governed_ai_provider_routing_readiness.id",
                "governed_ai_provider_routing_readiness.tenant_id",
                "governed_ai_provider_routing_readiness.organization_id",
                "governed_ai_provider_routing_readiness.connection_id",
            ],
            ondelete="RESTRICT",
            name="fk_ai_provider_canary_readiness_scope",
        ),
        UniqueConstraint(
            "tenant_id",
            "organization_id",
            "idempotency_key",
            name="uq_ai_provider_canary_event_idempotency",
        ),
        UniqueConstraint(
            "id",
            "tenant_id",
            "organization_id",
            "connection_id",
            name="uq_ai_provider_canary_event_id_scope",
        ),
        Index(
            "ix_ai_provider_canary_event_org_created",
            "organization_id",
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
    readiness_id: Mapped[str] = mapped_column(String(36), nullable=False)
    action: Mapped[str] = mapped_column(String(24), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    feature: Mapped[str] = mapped_column(
        String(80), nullable=False, default="intelligence_brief"
    )
    traffic_percentage: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_prompts_per_day: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    customer_prompts_allowed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    automatic_rollback_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    automatic_changes_allowed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    automatic_activation_allowed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    readiness_artifact_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    acknowledgements: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    reason_code: Mapped[str] = mapped_column(String(120), nullable=False)
    artifact_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )


class GovernedAIProviderCanaryAttempt(Base):
    """Immutable operational result for one selected private-AI prompt."""

    __tablename__ = "governed_ai_provider_canary_attempts"
    __table_args__ = (
        CheckConstraint(
            "outcome in ('private_succeeded','managed_fallback_succeeded',"
            "'managed_fallback_failed')",
            name="ck_ai_provider_canary_attempt_outcome",
        ),
        CheckConstraint(
            "feature = 'intelligence_brief' AND customer_prompt_sent = true "
            "AND automatic_changes_allowed = false AND platform_provider_cost = 0",
            name="ck_ai_provider_canary_attempt_boundary",
        ),
        CheckConstraint(
            "input_tokens >= 0 AND output_tokens >= 0 AND duration_ms >= 0 "
            "AND duration_ms <= 60000",
            name="ck_ai_provider_canary_attempt_usage",
        ),
        CheckConstraint(
            "(outcome = 'private_succeeded' AND managed_fallback_used = false "
            "AND automatic_rollback_triggered = false) OR "
            "(outcome != 'private_succeeded' AND managed_fallback_used = true "
            "AND automatic_rollback_triggered = true)",
            name="ck_ai_provider_canary_attempt_fallback",
        ),
        ForeignKeyConstraint(
            ["connection_id", "tenant_id", "organization_id"],
            [
                "governed_ai_provider_connections.id",
                "governed_ai_provider_connections.tenant_id",
                "governed_ai_provider_connections.organization_id",
            ],
            ondelete="RESTRICT",
            name="fk_ai_provider_canary_attempt_connection_scope",
        ),
        ForeignKeyConstraint(
            ["canary_event_id", "tenant_id", "organization_id", "connection_id"],
            [
                "governed_ai_provider_canary_events.id",
                "governed_ai_provider_canary_events.tenant_id",
                "governed_ai_provider_canary_events.organization_id",
                "governed_ai_provider_canary_events.connection_id",
            ],
            ondelete="RESTRICT",
            name="fk_ai_provider_canary_attempt_event_scope",
        ),
        UniqueConstraint(
            "tenant_id",
            "organization_id",
            "request_key_hash",
            name="uq_ai_provider_canary_attempt_request",
        ),
        Index(
            "ix_ai_provider_canary_attempt_org_created",
            "organization_id",
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
    canary_event_id: Mapped[str] = mapped_column(String(36), nullable=False)
    feature: Mapped[str] = mapped_column(String(80), nullable=False)
    outcome: Mapped[str] = mapped_column(String(40), nullable=False)
    request_key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    private_error_code: Mapped[str | None] = mapped_column(String(120))
    customer_prompt_sent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    provider_may_have_processed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    managed_fallback_used: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    automatic_rollback_triggered: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    automatic_changes_allowed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_owner: Mapped[str] = mapped_column(
        String(32), nullable=False, default="customer"
    )
    platform_provider_cost: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    artifact_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )


class GovernedAIProviderCanaryHealthSnapshot(Base):
    """Immutable multi-run health evidence; never routing authority."""

    __tablename__ = "governed_ai_provider_canary_health_snapshots"
    __table_args__ = (
        CheckConstraint(
            "status in ('collecting','eligible_for_later_review','blocked')",
            name="ck_ai_provider_canary_health_status",
        ),
        CheckConstraint(
            "feature = 'intelligence_brief' AND window_days = 30 "
            "AND required_success_days = 3 AND max_latency_threshold_ms = 8000",
            name="ck_ai_provider_canary_health_scope",
        ),
        CheckConstraint(
            "private_successes >= 0 AND distinct_success_days >= 0 "
            "AND managed_fallbacks >= 0 AND automatic_rollbacks >= 0 "
            "AND max_latency_ms >= 0 AND max_latency_ms <= 60000",
            name="ck_ai_provider_canary_health_counts",
        ),
        CheckConstraint(
            "traffic_change_allowed = false AND capability_change_allowed = false "
            "AND automatic_activation_allowed = false "
            "AND automatic_changes_allowed = false",
            name="ck_ai_provider_canary_health_no_authority",
        ),
        ForeignKeyConstraint(
            ["connection_id", "tenant_id", "organization_id"],
            [
                "governed_ai_provider_connections.id",
                "governed_ai_provider_connections.tenant_id",
                "governed_ai_provider_connections.organization_id",
            ],
            ondelete="RESTRICT",
            name="fk_ai_provider_canary_health_connection_scope",
        ),
        ForeignKeyConstraint(
            ["canary_event_id", "tenant_id", "organization_id", "connection_id"],
            [
                "governed_ai_provider_canary_events.id",
                "governed_ai_provider_canary_events.tenant_id",
                "governed_ai_provider_canary_events.organization_id",
                "governed_ai_provider_canary_events.connection_id",
            ],
            ondelete="RESTRICT",
            name="fk_ai_provider_canary_health_event_scope",
        ),
        UniqueConstraint(
            "tenant_id",
            "organization_id",
            "idempotency_key",
            name="uq_ai_provider_canary_health_idempotency",
        ),
        UniqueConstraint(
            "id",
            "tenant_id",
            "organization_id",
            "connection_id",
            name="uq_ai_provider_canary_health_id_scope",
        ),
        Index(
            "ix_ai_provider_canary_health_org_created",
            "organization_id",
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
    canary_event_id: Mapped[str] = mapped_column(String(36), nullable=False)
    feature: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    window_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    required_success_days: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    max_latency_threshold_ms: Mapped[int] = mapped_column(
        Integer, nullable=False, default=8000
    )
    private_successes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    distinct_success_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    managed_fallbacks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    automatic_rollbacks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    blockers: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    traffic_change_allowed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    capability_change_allowed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    automatic_activation_allowed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    automatic_changes_allowed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    artifact_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

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


class GovernedAIProviderCapabilityBenchmark(Base):
    """Immutable synthetic proof for one additional private-AI capability."""

    __tablename__ = "governed_ai_provider_capability_benchmarks"
    __table_args__ = (
        CheckConstraint(
            "capability in ('intelligence_question','intelligence_draft') "
            "AND case_count = 1",
            name="ck_ai_provider_capability_benchmark_scope",
        ),
        CheckConstraint(
            "status in ('passed','failed')",
            name="ck_ai_provider_capability_benchmark_status",
        ),
        CheckConstraint(
            "latency_ms >= 0 AND latency_ms <= 60000 "
            "AND input_tokens >= 0 AND output_tokens >= 0",
            name="ck_ai_provider_capability_benchmark_metrics",
        ),
        CheckConstraint(
            "customer_prompt_sent = false AND routing_enabled = false "
            "AND automatic_activation_allowed = false "
            "AND automatic_changes_allowed = false",
            name="ck_ai_provider_capability_benchmark_no_authority",
        ),
        ForeignKeyConstraint(
            ["connection_id", "tenant_id", "organization_id"],
            [
                "governed_ai_provider_connections.id",
                "governed_ai_provider_connections.tenant_id",
                "governed_ai_provider_connections.organization_id",
            ],
            ondelete="RESTRICT",
            name="fk_ai_provider_capability_benchmark_connection_scope",
        ),
        ForeignKeyConstraint(
            ["health_snapshot_id", "tenant_id", "organization_id", "connection_id"],
            [
                "governed_ai_provider_canary_health_snapshots.id",
                "governed_ai_provider_canary_health_snapshots.tenant_id",
                "governed_ai_provider_canary_health_snapshots.organization_id",
                "governed_ai_provider_canary_health_snapshots.connection_id",
            ],
            ondelete="RESTRICT",
            name="fk_ai_provider_capability_benchmark_health_scope",
        ),
        UniqueConstraint(
            "tenant_id",
            "organization_id",
            "idempotency_key",
            name="uq_ai_provider_capability_benchmark_idempotency",
        ),
        UniqueConstraint(
            "id",
            "tenant_id",
            "organization_id",
            "connection_id",
            name="uq_ai_provider_capability_benchmark_id_scope",
        ),
        Index(
            "ix_ai_provider_capability_benchmark_org_created",
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
    health_snapshot_id: Mapped[str] = mapped_column(String(36), nullable=False)
    capability: Mapped[str] = mapped_column(String(80), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(120), nullable=False)
    case_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    customer_prompt_sent: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    routing_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    automatic_activation_allowed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    automatic_changes_allowed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    health_artifact_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    connection_evidence_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    artifact_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )


class GovernedAIProviderCapabilityEvent(Base):
    """Append-only owner or safety decision for one fixed capability canary."""

    __tablename__ = "governed_ai_provider_capability_events"
    __table_args__ = (
        CheckConstraint(
            "action in ('enabled','disabled','automatic_rollback')",
            name="ck_ai_provider_capability_event_action",
        ),
        CheckConstraint(
            "capability in ('intelligence_question','intelligence_draft') "
            "AND max_prompts_per_day = 1",
            name="ck_ai_provider_capability_event_scope",
        ),
        CheckConstraint(
            "automatic_activation_allowed = false AND automatic_changes_allowed = false",
            name="ck_ai_provider_capability_event_no_authority",
        ),
        CheckConstraint(
            "(action = 'enabled' AND state = 'capability_canary' "
            "AND traffic_percentage = 5 AND customer_prompts_allowed = true "
            "AND automatic_rollback_enabled = true) OR "
            "(action != 'enabled' AND state = 'inactive' "
            "AND traffic_percentage = 0 AND customer_prompts_allowed = false)",
            name="ck_ai_provider_capability_event_state",
        ),
        ForeignKeyConstraint(
            ["connection_id", "tenant_id", "organization_id"],
            [
                "governed_ai_provider_connections.id",
                "governed_ai_provider_connections.tenant_id",
                "governed_ai_provider_connections.organization_id",
            ],
            ondelete="RESTRICT",
            name="fk_ai_provider_capability_event_connection_scope",
        ),
        ForeignKeyConstraint(
            ["health_snapshot_id", "tenant_id", "organization_id", "connection_id"],
            [
                "governed_ai_provider_canary_health_snapshots.id",
                "governed_ai_provider_canary_health_snapshots.tenant_id",
                "governed_ai_provider_canary_health_snapshots.organization_id",
                "governed_ai_provider_canary_health_snapshots.connection_id",
            ],
            ondelete="RESTRICT",
            name="fk_ai_provider_capability_event_health_scope",
        ),
        ForeignKeyConstraint(
            ["benchmark_id", "tenant_id", "organization_id", "connection_id"],
            [
                "governed_ai_provider_capability_benchmarks.id",
                "governed_ai_provider_capability_benchmarks.tenant_id",
                "governed_ai_provider_capability_benchmarks.organization_id",
                "governed_ai_provider_capability_benchmarks.connection_id",
            ],
            ondelete="RESTRICT",
            name="fk_ai_provider_capability_event_benchmark_scope",
        ),
        UniqueConstraint(
            "tenant_id",
            "organization_id",
            "idempotency_key",
            name="uq_ai_provider_capability_event_idempotency",
        ),
        UniqueConstraint(
            "id",
            "tenant_id",
            "organization_id",
            "connection_id",
            name="uq_ai_provider_capability_event_id_scope",
        ),
        Index(
            "ix_ai_provider_capability_event_org_created",
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
    health_snapshot_id: Mapped[str] = mapped_column(String(36), nullable=False)
    benchmark_id: Mapped[str] = mapped_column(String(36), nullable=False)
    action: Mapped[str] = mapped_column(String(24), nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False)
    capability: Mapped[str] = mapped_column(String(80), nullable=False)
    traffic_percentage: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_prompts_per_day: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    customer_prompts_allowed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    automatic_rollback_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    automatic_activation_allowed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    automatic_changes_allowed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
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


class GovernedAIProviderCapabilityAttempt(Base):
    """Immutable operational outcome for one selected capability prompt."""

    __tablename__ = "governed_ai_provider_capability_attempts"
    __table_args__ = (
        CheckConstraint(
            "outcome in ('private_succeeded','managed_fallback_succeeded',"
            "'managed_fallback_failed')",
            name="ck_ai_provider_capability_attempt_outcome",
        ),
        CheckConstraint(
            "capability in ('intelligence_question','intelligence_draft') "
            "AND customer_prompt_sent = true "
            "AND automatic_changes_allowed = false AND platform_provider_cost = 0",
            name="ck_ai_provider_capability_attempt_scope",
        ),
        CheckConstraint(
            "input_tokens >= 0 AND output_tokens >= 0 AND duration_ms >= 0 "
            "AND duration_ms <= 60000",
            name="ck_ai_provider_capability_attempt_metrics",
        ),
        CheckConstraint(
            "(outcome = 'private_succeeded' AND managed_fallback_used = false "
            "AND automatic_rollback_triggered = false) OR "
            "(outcome != 'private_succeeded' AND managed_fallback_used = true "
            "AND automatic_rollback_triggered = true)",
            name="ck_ai_provider_capability_attempt_fallback",
        ),
        ForeignKeyConstraint(
            ["connection_id", "tenant_id", "organization_id"],
            [
                "governed_ai_provider_connections.id",
                "governed_ai_provider_connections.tenant_id",
                "governed_ai_provider_connections.organization_id",
            ],
            ondelete="RESTRICT",
            name="fk_ai_provider_capability_attempt_connection_scope",
        ),
        ForeignKeyConstraint(
            ["capability_event_id", "tenant_id", "organization_id", "connection_id"],
            [
                "governed_ai_provider_capability_events.id",
                "governed_ai_provider_capability_events.tenant_id",
                "governed_ai_provider_capability_events.organization_id",
                "governed_ai_provider_capability_events.connection_id",
            ],
            ondelete="RESTRICT",
            name="fk_ai_provider_capability_attempt_event_scope",
        ),
        UniqueConstraint(
            "tenant_id",
            "organization_id",
            "request_key_hash",
            name="uq_ai_provider_capability_attempt_request",
        ),
        Index(
            "ix_ai_provider_capability_attempt_org_created",
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
    capability_event_id: Mapped[str] = mapped_column(String(36), nullable=False)
    capability: Mapped[str] = mapped_column(String(80), nullable=False)
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

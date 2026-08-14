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
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class GovernedExperimentPlan(Base):
    """A reviewable experiment design that cannot create live assignments."""

    __tablename__ = "governed_experiment_plans"
    __table_args__ = (
        CheckConstraint(
            "design_type in ('content_split','staggered_rollout','holdout_comparison')",
            name="ck_governed_experiment_plans_design_type",
        ),
        CheckConstraint(
            "status in ('draft','approved','rejected','cancelled')",
            name="ck_governed_experiment_plans_status",
        ),
        CheckConstraint(
            "minimum_sample_size >= 5 AND minimum_sample_size <= 1000",
            name="ck_governed_experiment_plans_sample_size",
        ),
        CheckConstraint(
            "observation_window_days >= 7 AND observation_window_days <= 180",
            name="ck_governed_experiment_plans_observation_window",
        ),
        UniqueConstraint(
            "tenant_id",
            "idempotency_key",
            name="uq_governed_experiment_plans_tenant_idempotency",
        ),
        Index(
            "ix_governed_experiment_plans_campaign_status_created",
            "campaign_id",
            "status",
            "created_at",
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
    campaign_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("campaigns.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    business_location_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("business_locations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    action_id: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    metric_id: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    measurement_contract_version: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
    )
    hypothesis: Mapped[str] = mapped_column(Text, nullable=False)
    design_type: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="draft",
        index=True,
    )
    minimum_sample_size: Mapped[int] = mapped_column(Integer, nullable=False)
    observation_window_days: Mapped[int] = mapped_column(Integer, nullable=False)
    guardrail_metric_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    eligibility_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    stop_rules: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    rollback_steps: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    design_version: Mapped[str] = mapped_column(String(40), nullable=False, default="1.0")
    artifact_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    reviewed_by_user_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
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


class GovernedExperimentProtocol(Base):
    """A frozen, separately authorized monitoring contract for an approved plan."""

    __tablename__ = "governed_experiment_protocols"
    __table_args__ = (
        CheckConstraint(
            "status in ('prepared','authorized','monitoring','stop_required','rollback_pending','rollback_verified','completed','cancelled')",
            name="ck_governed_experiment_protocols_status",
        ),
        UniqueConstraint(
            "tenant_id",
            "plan_id",
            name="uq_governed_experiment_protocols_tenant_plan",
        ),
        Index(
            "ix_governed_experiment_protocols_campaign_status_created",
            "campaign_id",
            "status",
            "created_at",
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
    campaign_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    business_location_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("business_locations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    plan_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("governed_experiment_plans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="prepared", index=True)
    protocol_version: Mapped[str] = mapped_column(String(40), nullable=False, default="1.0")
    plan_artifact_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    protocol_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    baseline_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    protected_baselines: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    allowance_baseline: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    stop_rules: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    rollback_steps: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    authorization_acknowledgements: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    change_evidence: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    latest_check_summary: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    stop_reason_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    stop_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    rollback_evidence: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    authorized_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    started_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    stopped_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    rollback_verified_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    authorized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    monitoring_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    observation_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rollback_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class GovernedExperimentGuardrailCheck(Base):
    """Append-only evidence from one protocol safety check."""

    __tablename__ = "governed_experiment_guardrail_checks"
    __table_args__ = (
        CheckConstraint(
            "status in ('passed','waiting_for_fresh_data','stop_required','completed')",
            name="ck_governed_experiment_guardrail_checks_status",
        ),
        Index(
            "ix_governed_experiment_checks_protocol_checked",
            "protocol_id",
            "checked_at",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    protocol_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("governed_experiment_protocols.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
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
    campaign_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    primary_metric: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    protected_metrics: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    allowance_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    triggered_rules: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    artifact_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    checked_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), index=True
    )

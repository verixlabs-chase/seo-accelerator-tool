from __future__ import annotations

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


class ActionPlanOccurrence(Base):
    """A dated, versioned occurrence of one canonical customer action."""

    __tablename__ = "action_plan_occurrences"
    __table_args__ = (
        CheckConstraint(
            "cadence in ('daily','weekly','monthly','later')",
            name="ck_action_plan_occurrences_cadence",
        ),
        CheckConstraint(
            "status in ('ready','in_progress','blocked','waiting_for_results','completed','dismissed','snoozed')",
            name="ck_action_plan_occurrences_status",
        ),
        UniqueConstraint(
            "tenant_id",
            "idempotency_key",
            name="uq_action_plan_occurrences_tenant_idempotency",
        ),
        Index(
            "ix_action_plan_occurrences_campaign_cadence_due",
            "campaign_id",
            "cadence",
            "due_at",
        ),
        Index(
            "ix_action_plan_occurrences_recommendation_status",
            "recommendation_id",
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
    recommendation_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("strategy_recommendations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    action_id: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    cadence: Mapped[str] = mapped_column(String(16), nullable=False)
    period_key: Mapped[str] = mapped_column(String(32), nullable=False)
    timezone: Mapped[str] = mapped_column(String(80), nullable=False, default="UTC")
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ready", index=True)
    lexicon_id: Mapped[str] = mapped_column(String(120), nullable=False)
    lexicon_version: Mapped[str] = mapped_column(String(80), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class ActionPlanStep(Base):
    """Persistent progress for one deterministic step in an action occurrence."""

    __tablename__ = "action_plan_steps"
    __table_args__ = (
        CheckConstraint(
            "status in ('not_started','in_progress','done','skipped','blocked')",
            name="ck_action_plan_steps_status",
        ),
        UniqueConstraint(
            "occurrence_id",
            "step_key",
            name="uq_action_plan_steps_occurrence_key",
        ),
        Index(
            "ix_action_plan_steps_occurrence_position",
            "occurrence_id",
            "position",
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
    occurrence_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("action_plan_occurrences.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    step_key: Mapped[str] = mapped_column(String(80), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    instruction: Mapped[str] = mapped_column(Text, nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="not_started", index=True)
    blocker_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    completed_by_user_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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


class ActionPlanMeasurement(Base):
    """Immutable action baseline plus the eventual measured result."""

    __tablename__ = "action_plan_measurements"
    __table_args__ = (
        CheckConstraint(
            "measurement_status in ('baseline_ready','insufficient_baseline','waiting_for_results','measured')",
            name="ck_action_plan_measurements_status",
        ),
        CheckConstraint(
            "outcome_status in ('pending','helped','did_not_help','insufficient_data')",
            name="ck_action_plan_measurements_outcome_status",
        ),
        UniqueConstraint(
            "occurrence_id",
            name="uq_action_plan_measurements_occurrence_id",
        ),
        Index(
            "ix_action_plan_measurements_campaign_status_due",
            "campaign_id",
            "measurement_status",
            "observation_due_at",
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
    occurrence_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("action_plan_occurrences.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    recommendation_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("strategy_recommendations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    action_id: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    measurement_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="insufficient_baseline",
        index=True,
    )
    outcome_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="pending",
        index=True,
    )
    success_metric_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    baseline_metrics: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    baseline_evidence: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    implementation_scope: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    completion_proof: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    outcome_metrics: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    outcome_evidence: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    observation_window_days: Mapped[int] = mapped_column(Integer, nullable=False)
    evidence_window_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    evidence_window_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    observation_due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    baseline_captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    work_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    outcome_measured_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    action_plan_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    lexicon_id: Mapped[str] = mapped_column(String(120), nullable=False)
    lexicon_version: Mapped[str] = mapped_column(String(80), nullable=False)
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


class ActionPlanForecast(Base):
    """Versioned direct-metric forecast for one measurable action plan."""

    __tablename__ = "action_plan_forecasts"
    __table_args__ = (
        CheckConstraint(
            "forecast_status in ('available','not_available')",
            name="ck_action_plan_forecasts_status",
        ),
        CheckConstraint(
            "data_quality in ('strong','moderate','insufficient')",
            name="ck_action_plan_forecasts_data_quality",
        ),
        UniqueConstraint(
            "occurrence_id",
            name="uq_action_plan_forecasts_occurrence_id",
        ),
        Index(
            "ix_action_plan_forecasts_campaign_status_generated",
            "campaign_id",
            "forecast_status",
            "generated_at",
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
    occurrence_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("action_plan_occurrences.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    measurement_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("action_plan_measurements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    recommendation_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("strategy_recommendations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    action_id: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    forecast_status: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    metric_forecasts: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    assumptions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    unavailable_reasons: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    data_quality: Mapped[str] = mapped_column(String(24), nullable=False)
    model_id: Mapped[str] = mapped_column(String(120), nullable=False)
    model_version: Mapped[str] = mapped_column(String(40), nullable=False)
    model_parameters: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    artifact_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    action_plan_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    lexicon_id: Mapped[str] = mapped_column(String(120), nullable=False)
    lexicon_version: Mapped[str] = mapped_column(String(80), nullable=False)
    observation_window_days: Mapped[int] = mapped_column(Integer, nullable=False)
    outcome_comparisons: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    compared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
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

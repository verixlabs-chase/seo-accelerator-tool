from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
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


class StandardsApproval(Base):
    """Append-only platform-owner decision over one sealed replay report."""

    __tablename__ = "standards_approvals"
    __table_args__ = (
        CheckConstraint(
            "decision in ('approved','rejected')",
            name="ck_standards_approvals_decision",
        ),
        Index("ix_standards_approvals_report_created", "replay_report_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    replay_report_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("standards_replay_reports.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    decision: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    replay_seal_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    candidate_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    rollout_plan_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    rollback_plan_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    acknowledges_new_baseline: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    decided_by_user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    automatic_activation_allowed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), index=True
    )


class StandardsRollout(Base):
    """Controlled activation and reversible state transition for an approved version."""

    __tablename__ = "standards_rollouts"
    __table_args__ = (
        CheckConstraint(
            "rollout_mode in ('immediate','scheduled')",
            name="ck_standards_rollouts_mode",
        ),
        CheckConstraint(
            "status in ('scheduled','in_progress','completed','failed','rolled_back')",
            name="ck_standards_rollouts_status",
        ),
        Index("ix_standards_rollouts_status_scheduled", "status", "scheduled_for"),
        Index("ix_standards_rollouts_artifact_created", "artifact_type", "artifact_key", "created_at"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    approval_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("standards_approvals.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    artifact_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    artifact_key: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    base_version: Mapped[str] = mapped_column(String(40), nullable=False)
    candidate_version: Mapped[str] = mapped_column(String(40), nullable=False)
    rollout_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="scheduled", index=True)
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    provider_metric_contract_version_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("provider_metric_contract_versions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    previous_provider_metric_contract_version_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("provider_metric_contract_versions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    reference_library_version_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("reference_library_versions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    previous_reference_library_version_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("reference_library_versions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    created_by_user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    rolled_back_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    rolled_back_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rollback_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    automatic_activation_allowed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )


class PerformanceDriftEvent(Base):
    """Minimized cross-organization evidence of unusual shared movement."""

    __tablename__ = "performance_drift_events"
    __table_args__ = (
        CheckConstraint(
            "label in ('possible_ecosystem_change','unusual_shared_movement')",
            name="ck_performance_drift_events_label",
        ),
        CheckConstraint(
            "direction in ('up','down')",
            name="ck_performance_drift_events_direction",
        ),
        CheckConstraint(
            "status in ('needs_review','investigating','dismissed','resolved')",
            name="ck_performance_drift_events_status",
        ),
        CheckConstraint(
            "sample_size >= 0 and organization_count >= 0",
            name="ck_performance_drift_events_sample_counts",
        ),
        UniqueConstraint(
            "detector_version",
            "metric_contract_id",
            "comparison_scope_hash",
            "comparison_end",
            "evidence_digest",
            name="uq_performance_drift_events_detector_evidence",
        ),
        Index(
            "ix_performance_drift_events_status_created",
            "status",
            "created_at",
        ),
        Index(
            "ix_performance_drift_events_contract_period",
            "metric_contract_id",
            "comparison_end",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    detector_version: Mapped[str] = mapped_column(String(40), nullable=False)
    label: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="needs_review", index=True
    )
    provider_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    metric_family: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    metric_contract_id: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    metric_contract_version: Mapped[str] = mapped_column(String(40), nullable=False)
    comparison_scope_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    baseline_start: Mapped[date] = mapped_column(Date, nullable=False)
    baseline_end: Mapped[date] = mapped_column(Date, nullable=False)
    comparison_start: Mapped[date] = mapped_column(Date, nullable=False)
    comparison_end: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False)
    organization_count: Mapped[int] = mapped_column(Integer, nullable=False)
    excluded_sample_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    direction: Mapped[str] = mapped_column(String(12), nullable=False)
    median_change: Mapped[float] = mapped_column(Float, nullable=False)
    confidence_low: Mapped[float] = mapped_column(Float, nullable=False)
    confidence_high: Mapped[float] = mapped_column(Float, nullable=False)
    agreement_ratio: Mapped[float] = mapped_column(Float, nullable=False)
    cohort_rules: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    known_confounders: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    affected_metric_families: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    plain_language_summary: Mapped[str] = mapped_column(Text, nullable=False)
    investigation_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    automatic_activation_allowed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

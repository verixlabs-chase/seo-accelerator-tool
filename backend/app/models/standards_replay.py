from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class StandardsReplayReport(Base):
    """Immutable replay evidence for a proposed standards or metric-contract version."""

    __tablename__ = "standards_replay_reports"
    __table_args__ = (
        CheckConstraint(
            "artifact_type in ('provider_metric_contract','intelligence_lexicon')",
            name="ck_standards_replay_reports_artifact_type",
        ),
        CheckConstraint(
            "sample_type in ('fixed_fixture','approved_evidence','combined')",
            name="ck_standards_replay_reports_sample_type",
        ),
        CheckConstraint(
            "status in ('passed','changed','blocked','failed')",
            name="ck_standards_replay_reports_status",
        ),
        Index(
            "ix_standards_replay_reports_artifact_created",
            "artifact_type",
            "artifact_key",
            "created_at",
        ),
        Index(
            "ix_standards_replay_reports_change_created",
            "standards_change_candidate_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    standards_change_candidate_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("standards_change_candidates.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    provider_metric_contract_version_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("provider_metric_contract_versions.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    reference_library_version_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("reference_library_versions.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    artifact_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    artifact_key: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    base_version: Mapped[str] = mapped_column(String(40), nullable=False)
    candidate_version: Mapped[str] = mapped_column(String(40), nullable=False)
    replay_version: Mapped[str] = mapped_column(String(40), nullable=False)
    fixture_set_version: Mapped[str] = mapped_column(String(40), nullable=False)
    sample_type: Mapped[str] = mapped_column(String(30), nullable=False)
    sample_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    approval_reference_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tenant_safe_sample: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    total_cases: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    changed_diagnoses: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    changed_actions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    changed_forecasts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    changed_results: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    newly_unknown_results: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    invalidated_comparisons: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    requires_new_baseline: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    definition_diff_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    impact_report_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    replay_results_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    automatic_activation_allowed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    executed_by_user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), index=True
    )

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LaunchReadinessProof(Base):
    """Append-only, platform-owned evidence for one manual launch gate."""

    __tablename__ = "launch_readiness_proofs"
    __table_args__ = (
        CheckConstraint(
            "gate_code in ('critical_journeys','recovery_drills','customer_communications',"
            "'first_use_comprehension','known_limitations')",
            name="ck_launch_readiness_proofs_gate",
        ),
        CheckConstraint(
            "result in ('passed','failed')",
            name="ck_launch_readiness_proofs_result",
        ),
        CheckConstraint(
            "proof_kind in ('production_smoke','recovery_drill','communication_test',"
            "'moderated_test','capability_review')",
            name="ck_launch_readiness_proofs_kind",
        ),
        CheckConstraint(
            "expires_at > observed_at",
            name="ck_launch_readiness_proofs_expiry",
        ),
        UniqueConstraint("evidence_digest", name="uq_launch_readiness_proofs_digest"),
        Index(
            "ix_launch_readiness_proofs_gate_observed",
            "gate_code",
            "observed_at",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    schema_version: Mapped[str] = mapped_column(
        String(40), nullable=False, default="ops1-launch-proof-v1"
    )
    gate_code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    result: Mapped[str] = mapped_column(String(12), nullable=False, index=True)
    proof_kind: Mapped[str] = mapped_column(String(30), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_reference: Mapped[str] = mapped_column(String(160), nullable=False)
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    recorded_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), index=True
    )


class LaunchReadinessDecision(Base):
    """Append-only platform-owner decision over one exact readiness snapshot."""

    __tablename__ = "launch_readiness_decisions"
    __table_args__ = (
        CheckConstraint(
            "decision in ('go','no_go')",
            name="ck_launch_readiness_decisions_decision",
        ),
        CheckConstraint(
            "length(basis_digest) = 64 and length(decision_digest) = 64",
            name="ck_launch_readiness_decisions_digests",
        ),
        UniqueConstraint("decision_digest", name="uq_launch_readiness_decisions_digest"),
        Index("ix_launch_readiness_decisions_created", "created_at"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    schema_version: Mapped[str] = mapped_column(
        String(40), nullable=False, default="ops1-launch-decision-v1"
    )
    decision: Mapped[str] = mapped_column(String(12), nullable=False, index=True)
    basis_digest: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    release_reference: Mapped[str] = mapped_column(String(120), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    known_limitations_acknowledged: Mapped[bool] = mapped_column(Boolean, nullable=False)
    support_owner_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    rollback_owner_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    evidence_current_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    decision_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    decided_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

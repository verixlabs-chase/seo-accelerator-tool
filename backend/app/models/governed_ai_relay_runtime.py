from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class GovernedAIRelayRuntimeDiscovery(Base):
    __tablename__ = "governed_ai_relay_runtime_discoveries"
    __table_args__ = (
        CheckConstraint(
            "runtime_kind in ('not_found','ollama','lm_studio','multiple')",
            name="ck_governed_ai_relay_runtime_kind",
        ),
        CheckConstraint(
            "model_count >= 0 AND model_count <= 1000 "
            "AND length(request_signature_hash) = 64 "
            "AND length(artifact_hash) = 64",
            name="ck_governed_ai_relay_runtime_counts_hashes",
        ),
        CheckConstraint(
            "loopback_only = true "
            "AND customer_data_sent = false "
            "AND model_called = false "
            "AND model_identifiers_included = false",
            name="ck_governed_ai_relay_runtime_discovery_only",
        ),
        CheckConstraint(
            "(runtime_kind = 'not_found' AND ollama_detected = false "
            "AND lm_studio_detected = false AND model_count = 0) OR "
            "(runtime_kind = 'ollama' AND ollama_detected = true "
            "AND lm_studio_detected = false) OR "
            "(runtime_kind = 'lm_studio' AND ollama_detected = false "
            "AND lm_studio_detected = true) OR "
            "(runtime_kind = 'multiple' AND ollama_detected = true "
            "AND lm_studio_detected = true)",
            name="ck_governed_ai_relay_runtime_detection_truth",
        ),
        ForeignKeyConstraint(
            ["enrollment_id", "tenant_id", "organization_id"],
            [
                "governed_ai_relay_enrollments.id",
                "governed_ai_relay_enrollments.tenant_id",
                "governed_ai_relay_enrollments.organization_id",
            ],
            ondelete="RESTRICT",
            name="fk_governed_ai_relay_runtime_enrollment_scope",
        ),
        UniqueConstraint(
            "id",
            "tenant_id",
            "organization_id",
            "enrollment_id",
            name="uq_governed_ai_relay_runtime_id_scope",
        ),
        Index(
            "ix_governed_ai_relay_runtime_enrollment_received",
            "enrollment_id",
            "received_at",
        ),
        Index("ix_governed_ai_relay_runtime_artifact_hash", "artifact_hash"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    enrollment_id: Mapped[str] = mapped_column(String(36), nullable=False)
    agent_version: Mapped[str] = mapped_column(String(30), nullable=False)
    runtime_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    model_count: Mapped[int] = mapped_column(Integer, nullable=False)
    ollama_detected: Mapped[bool] = mapped_column(Boolean, nullable=False)
    lm_studio_detected: Mapped[bool] = mapped_column(Boolean, nullable=False)
    loopback_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    customer_data_sent: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    model_called: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    model_identifiers_included: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    request_signature_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    artifact_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

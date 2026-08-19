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


class GovernedAIRelayModelQualification(Base):
    __tablename__ = "governed_ai_relay_model_qualifications"
    __table_args__ = (
        CheckConstraint(
            "runtime_kind in ('ollama','lm_studio') "
            "AND status in ('passed','failed') "
            "AND prompt_version = 'local-model-synthetic-v1'",
            name="ck_governed_ai_relay_qualification_contract",
        ),
        CheckConstraint(
            "latency_ms >= 0 AND latency_ms <= 120000 "
            "AND length(local_model_fingerprint) = 64 "
            "AND length(request_signature_hash) = 64 "
            "AND length(artifact_hash) = 64",
            name="ck_governed_ai_relay_qualification_bounds",
        ),
        CheckConstraint(
            "synthetic_input_only = true AND model_call_attempted = true "
            "AND customer_data_sent = false "
            "AND raw_model_identifier_sent = false "
            "AND model_output_sent = false "
            "AND customer_work_allowed = false "
            "AND publishing_allowed = false",
            name="ck_governed_ai_relay_qualification_safety",
        ),
        CheckConstraint(
            "status = 'failed' OR "
            "(model_response_received = true AND output_json_valid = true "
            "AND required_contract_matched = true)",
            name="ck_governed_ai_relay_qualification_pass_truth",
        ),
        ForeignKeyConstraint(
            ["enrollment_id", "tenant_id", "organization_id"],
            [
                "governed_ai_relay_enrollments.id",
                "governed_ai_relay_enrollments.tenant_id",
                "governed_ai_relay_enrollments.organization_id",
            ],
            ondelete="RESTRICT",
            name="fk_governed_ai_relay_qualification_enrollment_scope",
        ),
        UniqueConstraint(
            "id",
            "tenant_id",
            "organization_id",
            "enrollment_id",
            name="uq_governed_ai_relay_qualification_id_scope",
        ),
        Index(
            "ix_governed_ai_relay_qualification_enrollment_received",
            "enrollment_id",
            "received_at",
        ),
        Index(
            "ix_governed_ai_relay_qualification_fingerprint",
            "local_model_fingerprint",
        ),
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
    local_model_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(60), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    output_json_valid: Mapped[bool] = mapped_column(Boolean, nullable=False)
    required_contract_matched: Mapped[bool] = mapped_column(Boolean, nullable=False)
    synthetic_input_only: Mapped[bool] = mapped_column(Boolean, nullable=False)
    model_call_attempted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    model_response_received: Mapped[bool] = mapped_column(Boolean, nullable=False)
    customer_data_sent: Mapped[bool] = mapped_column(Boolean, nullable=False)
    raw_model_identifier_sent: Mapped[bool] = mapped_column(Boolean, nullable=False)
    model_output_sent: Mapped[bool] = mapped_column(Boolean, nullable=False)
    customer_work_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    publishing_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    request_signature_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    artifact_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

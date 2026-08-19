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
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class GovernedAIRelayDiagnosticPacket(Base):
    __tablename__ = "governed_ai_relay_diagnostic_packets"
    __table_args__ = (
        CheckConstraint(
            "packet_kind = 'synthetic_connection_challenge'",
            name="ck_governed_ai_relay_packet_kind",
        ),
        CheckConstraint(
            "length(expected_response_hash) = 64 "
            "AND length(artifact_hash) = 64 "
            "AND length(request_id_hash) = 64",
            name="ck_governed_ai_relay_packet_hashes",
        ),
        CheckConstraint(
            "customer_data_included = false "
            "AND model_execution_requested = false "
            "AND database_access_requested = false "
            "AND business_execution_requested = false "
            "AND publishing_requested = false",
            name="ck_governed_ai_relay_packet_synthetic_only",
        ),
        CheckConstraint(
            "expires_at > created_at",
            name="ck_governed_ai_relay_packet_expiry",
        ),
        ForeignKeyConstraint(
            ["enrollment_id", "tenant_id", "organization_id"],
            [
                "governed_ai_relay_enrollments.id",
                "governed_ai_relay_enrollments.tenant_id",
                "governed_ai_relay_enrollments.organization_id",
            ],
            ondelete="RESTRICT",
            name="fk_governed_ai_relay_packet_enrollment_scope",
        ),
        UniqueConstraint(
            "tenant_id",
            "organization_id",
            "enrollment_id",
            "request_id_hash",
            name="uq_governed_ai_relay_packet_request",
        ),
        UniqueConstraint(
            "id",
            "tenant_id",
            "organization_id",
            "enrollment_id",
            name="uq_governed_ai_relay_packet_id_scope",
        ),
        Index(
            "ix_governed_ai_relay_packet_enrollment_created",
            "enrollment_id",
            "created_at",
        ),
        Index("ix_governed_ai_relay_packet_artifact_hash", "artifact_hash"),
        Index("ix_governed_ai_relay_packet_expires_at", "expires_at"),
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
    enrollment_id: Mapped[str] = mapped_column(String(36), nullable=False)
    protocol_version: Mapped[str] = mapped_column(String(60), nullable=False)
    packet_kind: Mapped[str] = mapped_column(String(60), nullable=False)
    challenge_nonce: Mapped[str] = mapped_column(String(64), nullable=False)
    expected_response_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    artifact_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    request_id_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    customer_data_included: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    model_execution_requested: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    database_access_requested: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    business_execution_requested: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    publishing_requested: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    created_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class GovernedAIRelayDiagnosticAcknowledgement(Base):
    __tablename__ = "governed_ai_relay_diagnostic_acknowledgements"
    __table_args__ = (
        CheckConstraint(
            "length(response_hash) = 64 "
            "AND length(request_signature_hash) = 64 "
            "AND length(packet_artifact_hash) = 64 "
            "AND length(artifact_hash) = 64",
            name="ck_governed_ai_relay_ack_hashes",
        ),
        CheckConstraint(
            "customer_data_processed = false "
            "AND model_called = false "
            "AND database_accessed = false "
            "AND business_work_executed = false "
            "AND publishing_performed = false",
            name="ck_governed_ai_relay_ack_synthetic_only",
        ),
        ForeignKeyConstraint(
            ["packet_id", "tenant_id", "organization_id", "enrollment_id"],
            [
                "governed_ai_relay_diagnostic_packets.id",
                "governed_ai_relay_diagnostic_packets.tenant_id",
                "governed_ai_relay_diagnostic_packets.organization_id",
                "governed_ai_relay_diagnostic_packets.enrollment_id",
            ],
            ondelete="RESTRICT",
            name="fk_governed_ai_relay_ack_packet_scope",
        ),
        UniqueConstraint(
            "packet_id",
            name="uq_governed_ai_relay_ack_packet",
        ),
        UniqueConstraint(
            "id",
            "tenant_id",
            "organization_id",
            name="uq_governed_ai_relay_ack_id_scope",
        ),
        Index(
            "ix_governed_ai_relay_ack_enrollment_created",
            "enrollment_id",
            "acknowledged_at",
        ),
        Index("ix_governed_ai_relay_ack_artifact_hash", "artifact_hash"),
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
    enrollment_id: Mapped[str] = mapped_column(String(36), nullable=False)
    packet_id: Mapped[str] = mapped_column(String(36), nullable=False)
    response_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    request_signature_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    packet_artifact_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    artifact_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    customer_data_processed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    model_called: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    database_accessed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    business_work_executed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    publishing_performed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    acknowledged_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

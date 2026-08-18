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


class GovernedAIProviderBenchmark(Base):
    """Append-only synthetic quality evidence for an inactive provider candidate."""

    __tablename__ = "governed_ai_provider_benchmarks"
    __table_args__ = (
        CheckConstraint(
            "status in ('passed','failed')",
            name="ck_governed_ai_provider_benchmarks_status",
        ),
        CheckConstraint(
            "case_count = 3 AND passed_case_count >= 0 "
            "AND passed_case_count <= case_count",
            name="ck_governed_ai_provider_benchmarks_case_counts",
        ),
        CheckConstraint(
            "median_latency_ms >= 0 AND median_latency_ms <= 60000",
            name="ck_governed_ai_provider_benchmarks_latency",
        ),
        CheckConstraint(
            "reported_input_tokens >= 0 AND reported_output_tokens >= 0",
            name="ck_governed_ai_provider_benchmarks_tokens",
        ),
        CheckConstraint(
            "automatic_activation_allowed = false",
            name="ck_governed_ai_provider_benchmarks_no_activation",
        ),
        ForeignKeyConstraint(
            ["connection_id", "tenant_id", "organization_id"],
            [
                "governed_ai_provider_connections.id",
                "governed_ai_provider_connections.tenant_id",
                "governed_ai_provider_connections.organization_id",
            ],
            ondelete="RESTRICT",
            name="fk_governed_ai_provider_benchmarks_connection_scope",
        ),
        UniqueConstraint(
            "tenant_id",
            "organization_id",
            "connection_id",
            "idempotency_key",
            name="uq_governed_ai_provider_benchmarks_scope_idempotency",
        ),
        UniqueConstraint(
            "id",
            "tenant_id",
            "organization_id",
            "connection_id",
            name="uq_ai_provider_benchmarks_id_scope",
        ),
        Index(
            "ix_governed_ai_provider_benchmarks_connection_created",
            "connection_id",
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
    benchmark_version: Mapped[str] = mapped_column(String(60), nullable=False)
    connection_evidence_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    case_count: Mapped[int] = mapped_column(Integer, nullable=False)
    passed_case_count: Mapped[int] = mapped_column(Integer, nullable=False)
    median_latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    reported_input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reported_output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    case_results: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    evidence_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    artifact_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)
    automatic_activation_allowed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    created_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

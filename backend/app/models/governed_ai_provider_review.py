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
    JSON,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class GovernedAIProviderReview(Base):
    """Append-only owner decision that cannot activate or route to a provider."""

    __tablename__ = "governed_ai_provider_reviews"
    __table_args__ = (
        CheckConstraint(
            "decision in ('approved_for_future_activation','rejected')",
            name="ck_governed_ai_provider_reviews_decision",
        ),
        CheckConstraint(
            "automatic_activation_allowed = false",
            name="ck_governed_ai_provider_reviews_no_activation",
        ),
        ForeignKeyConstraint(
            ["connection_id", "tenant_id", "organization_id"],
            [
                "governed_ai_provider_connections.id",
                "governed_ai_provider_connections.tenant_id",
                "governed_ai_provider_connections.organization_id",
            ],
            ondelete="RESTRICT",
            name="fk_ai_provider_reviews_connection_scope",
        ),
        ForeignKeyConstraint(
            ["benchmark_id", "tenant_id", "organization_id", "connection_id"],
            [
                "governed_ai_provider_benchmarks.id",
                "governed_ai_provider_benchmarks.tenant_id",
                "governed_ai_provider_benchmarks.organization_id",
                "governed_ai_provider_benchmarks.connection_id",
            ],
            ondelete="RESTRICT",
            name="fk_ai_provider_reviews_benchmark_scope",
        ),
        UniqueConstraint(
            "tenant_id",
            "organization_id",
            "benchmark_id",
            name="uq_ai_provider_reviews_benchmark",
        ),
        UniqueConstraint(
            "id",
            "tenant_id",
            "organization_id",
            "connection_id",
            "benchmark_id",
            name="uq_ai_provider_reviews_id_scope",
        ),
        Index(
            "ix_ai_provider_reviews_connection_reviewed",
            "connection_id",
            "reviewed_at",
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
    benchmark_id: Mapped[str] = mapped_column(String(36), nullable=False)
    decision: Mapped[str] = mapped_column(String(40), nullable=False)
    benchmark_artifact_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    connection_evidence_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    acknowledgements: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    decision_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    automatic_activation_allowed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    reviewed_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    reviewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

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


class GovernedAIProviderStandbyEvent(Base):
    """Append-only zero-traffic standby registration or removal."""

    __tablename__ = "governed_ai_provider_standby_events"
    __table_args__ = (
        CheckConstraint(
            "action in ('enabled','disabled')",
            name="ck_ai_provider_standby_events_action",
        ),
        CheckConstraint(
            "managed_backend = 'mistral'",
            name="ck_ai_provider_standby_events_managed_backend",
        ),
        CheckConstraint(
            "routing_mode = 'zero_traffic_standby' AND traffic_percentage = 0",
            name="ck_ai_provider_standby_events_zero_traffic",
        ),
        CheckConstraint(
            "customer_prompts_allowed = false AND automatic_changes_allowed = false "
            "AND automatic_activation_allowed = false",
            name="ck_ai_provider_standby_events_no_authority",
        ),
        ForeignKeyConstraint(
            ["connection_id", "tenant_id", "organization_id"],
            [
                "governed_ai_provider_connections.id",
                "governed_ai_provider_connections.tenant_id",
                "governed_ai_provider_connections.organization_id",
            ],
            ondelete="RESTRICT",
            name="fk_ai_provider_standby_events_connection_scope",
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
            name="fk_ai_provider_standby_events_benchmark_scope",
        ),
        ForeignKeyConstraint(
            [
                "review_id",
                "tenant_id",
                "organization_id",
                "connection_id",
                "benchmark_id",
            ],
            [
                "governed_ai_provider_reviews.id",
                "governed_ai_provider_reviews.tenant_id",
                "governed_ai_provider_reviews.organization_id",
                "governed_ai_provider_reviews.connection_id",
                "governed_ai_provider_reviews.benchmark_id",
            ],
            ondelete="RESTRICT",
            name="fk_ai_provider_standby_events_review_scope",
        ),
        UniqueConstraint(
            "tenant_id",
            "organization_id",
            "idempotency_key",
            name="uq_ai_provider_standby_events_idempotency",
        ),
        UniqueConstraint(
            "id",
            "tenant_id",
            "organization_id",
            "connection_id",
            name="uq_ai_provider_standby_events_id_scope",
        ),
        Index(
            "ix_ai_provider_standby_events_org_created",
            "organization_id",
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
    benchmark_id: Mapped[str] = mapped_column(String(36), nullable=False)
    review_id: Mapped[str] = mapped_column(String(36), nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    managed_backend: Mapped[str] = mapped_column(
        String(32), nullable=False, default="mistral"
    )
    routing_mode: Mapped[str] = mapped_column(
        String(40), nullable=False, default="zero_traffic_standby"
    )
    traffic_percentage: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    customer_prompts_allowed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    automatic_changes_allowed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    automatic_activation_allowed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    benchmark_artifact_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    connection_evidence_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    review_decision_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    acknowledgements: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    artifact_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

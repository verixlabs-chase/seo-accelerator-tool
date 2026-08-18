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
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class GovernedAIProviderConnection(Base):
    __tablename__ = "governed_ai_provider_connections"
    __table_args__ = (
        CheckConstraint(
            "adapter_type = 'openai_compatible'",
            name="ck_governed_ai_provider_connections_adapter",
        ),
        CheckConstraint(
            "status in ('candidate','disconnected')",
            name="ck_governed_ai_provider_connections_status",
        ),
        CheckConstraint(
            "validation_status in ('not_tested','failed','passed')",
            name="ck_governed_ai_provider_connections_validation",
        ),
        CheckConstraint(
            "network_validation_status in ('not_tested','failed','passed')",
            name="ck_governed_ai_provider_connections_network_validation",
        ),
        CheckConstraint(
            "last_validation_latency_ms is null OR "
            "(last_validation_latency_ms >= 0 AND last_validation_latency_ms <= 60000)",
            name="ck_governed_ai_provider_connections_validation_latency",
        ),
        CheckConstraint(
            "activation_status = 'inactive' AND automatic_activation_allowed = false",
            name="ck_governed_ai_provider_connections_inactive",
        ),
        UniqueConstraint(
            "tenant_id",
            "organization_id",
            "name",
            name="uq_governed_ai_provider_connections_scope_name",
        ),
        UniqueConstraint(
            "id",
            "tenant_id",
            "organization_id",
            name="uq_governed_ai_provider_connections_id_scope",
        ),
        Index(
            "ix_governed_ai_provider_connections_scope_status",
            "tenant_id",
            "organization_id",
            "status",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    adapter_type: Mapped[str] = mapped_column(
        String(40), nullable=False, default="openai_compatible"
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="candidate")
    endpoint_host: Mapped[str] = mapped_column(String(253), nullable=False)
    model_identifier: Mapped[str] = mapped_column(String(200), nullable=False)
    capabilities_json: Mapped[str] = mapped_column(Text, nullable=False)
    encrypted_config_blob: Mapped[str | None] = mapped_column(Text, nullable=True)
    key_reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    key_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    credential_configured: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    validation_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="not_tested"
    )
    network_validation_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="not_tested"
    )
    last_validation_reason: Mapped[str | None] = mapped_column(String(80))
    resolved_address_hash: Mapped[str | None] = mapped_column(String(64))
    last_validation_latency_ms: Mapped[int | None] = mapped_column(Integer)
    validation_schema_version: Mapped[str | None] = mapped_column(String(60))
    validation_evidence_hash: Mapped[str | None] = mapped_column(String(64))
    activation_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="inactive"
    )
    automatic_activation_allowed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    created_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL")
    )
    disconnected_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL")
    )
    disconnected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

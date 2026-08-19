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
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class GovernedAIRelayEnrollment(Base):
    __tablename__ = "governed_ai_relay_enrollments"
    __table_args__ = (
        CheckConstraint(
            "status in ('active','revoked')",
            name="ck_governed_ai_relay_enrollment_status",
        ),
        CheckConstraint(
            "length(token_hash) = 64 AND heartbeat_count >= 0",
            name="ck_governed_ai_relay_enrollment_token_usage",
        ),
        CheckConstraint(
            "customer_prompts_allowed = false "
            "AND decision_packets_enabled = false "
            "AND database_access_allowed = false "
            "AND execution_allowed = false "
            "AND publishing_allowed = false",
            name="ck_governed_ai_relay_enrollment_connection_only",
        ),
        CheckConstraint(
            "(status = 'active' AND revoked_at IS NULL) OR "
            "(status = 'revoked' AND revoked_at IS NOT NULL)",
            name="ck_governed_ai_relay_enrollment_revocation",
        ),
        UniqueConstraint(
            "tenant_id",
            "organization_id",
            "request_id_hash",
            name="uq_governed_ai_relay_enrollment_request",
        ),
        UniqueConstraint(
            "id",
            "tenant_id",
            "organization_id",
            name="uq_governed_ai_relay_enrollment_id_scope",
        ),
        Index(
            "ix_governed_ai_relay_enrollment_org_status",
            "organization_id",
            "status",
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
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    protocol_version: Mapped[str] = mapped_column(String(60), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    token_hint: Mapped[str] = mapped_column(String(16), nullable=False)
    request_id_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    customer_prompts_allowed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    decision_packets_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    database_access_allowed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    execution_allowed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    publishing_allowed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    heartbeat_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT")
    )
    revoked_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

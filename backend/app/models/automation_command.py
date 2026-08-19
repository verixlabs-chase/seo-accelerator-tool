from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AutomationServiceAccount(Base):
    __tablename__ = "automation_service_accounts"
    __table_args__ = (
        CheckConstraint(
            "status in ('active','revoked')",
            name="ck_automation_service_accounts_status",
        ),
        CheckConstraint(
            "length(token_hash) = 64 AND token_version >= 1",
            name="ck_automation_service_accounts_token",
        ),
        CheckConstraint(
            "(status = 'active' AND revoked_at IS NULL) OR "
            "(status = 'revoked' AND revoked_at IS NOT NULL)",
            name="ck_automation_service_accounts_revocation",
        ),
        ForeignKeyConstraint(
            ["business_location_id", "organization_id"],
            ["business_locations.id", "business_locations.organization_id"],
            name="fk_automation_service_accounts_location_scope",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "id",
            "tenant_id",
            "organization_id",
            name="uq_automation_service_accounts_id_scope",
        ),
        Index(
            "ix_automation_service_accounts_org_status",
            "organization_id",
            "status",
            "created_at",
        ),
        Index(
            "uq_automation_service_accounts_one_active_org",
            "organization_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
            sqlite_where=text("status = 'active'"),
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
    business_location_id: Mapped[str] = mapped_column(String(36), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    token_hint: Mapped[str] = mapped_column(String(16), nullable=False)
    token_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    allowed_commands_json: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    revoked_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AutomationCommandReceipt(Base):
    __tablename__ = "automation_command_receipts"
    __table_args__ = (
        CheckConstraint(
            "command_type in ('report.retrieve','report.generate_saved','recommendation.retrieve','recommendation.request_review','connection.refresh_saved')",
            name="ck_automation_command_receipts_type",
        ),
        CheckConstraint(
            "status in ('succeeded','denied')",
            name="ck_automation_command_receipts_status",
        ),
        CheckConstraint(
            "length(request_hash) = 64 AND length(artifact_hash) = 64",
            name="ck_automation_command_receipts_hashes",
        ),
        ForeignKeyConstraint(
            ["service_account_id", "tenant_id", "organization_id"],
            [
                "automation_service_accounts.id",
                "automation_service_accounts.tenant_id",
                "automation_service_accounts.organization_id",
            ],
            name="fk_automation_command_receipts_account_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["recommendation_id", "tenant_id", "campaign_id"],
            [
                "strategy_recommendations.id",
                "strategy_recommendations.tenant_id",
                "strategy_recommendations.campaign_id",
            ],
            name="fk_automation_command_receipts_recommendation_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["business_location_id", "organization_id"],
            ["business_locations.id", "business_locations.organization_id"],
            name="fk_automation_command_receipts_location_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["campaign_id", "tenant_id", "organization_id", "business_location_id"],
            [
                "campaigns.id",
                "campaigns.tenant_id",
                "campaigns.organization_id",
                "campaigns.business_location_id",
            ],
            name="fk_automation_command_receipts_campaign_scope",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "service_account_id",
            "idempotency_key",
            name="uq_automation_command_receipts_idempotency",
        ),
        UniqueConstraint(
            "id",
            "tenant_id",
            "organization_id",
            name="uq_automation_command_receipts_id_scope",
        ),
        Index(
            "ix_automation_command_receipts_org_created",
            "organization_id",
            "created_at",
        ),
        Index(
            "ix_automation_command_receipts_account_created",
            "service_account_id",
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
    service_account_id: Mapped[str] = mapped_column(String(36), nullable=False)
    business_location_id: Mapped[str] = mapped_column(String(36), nullable=False)
    campaign_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    report_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    recommendation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    schema_version: Mapped[str] = mapped_column(String(80), nullable=False)
    command_type: Mapped[str] = mapped_column(String(60), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(120), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    denial_reason_code: Mapped[str | None] = mapped_column(String(100))
    result_json: Mapped[str] = mapped_column(Text, nullable=False)
    artifact_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

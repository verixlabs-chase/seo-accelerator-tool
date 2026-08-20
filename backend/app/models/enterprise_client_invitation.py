from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EnterpriseClientInvitation(Base):
    __tablename__ = "enterprise_client_invitations"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "email_hash",
            "location_group_id",
            name="uq_enterprise_client_invites_org_email_group",
        ),
        ForeignKeyConstraint(
            ["location_group_id", "organization_id"],
            ["portfolio_location_groups.id", "portfolio_location_groups.organization_id"],
            ondelete="RESTRICT",
            name="fk_enterprise_client_invites_group_org",
        ),
        CheckConstraint("tenant_id = organization_id", name="ck_enterprise_client_invites_scope"),
        CheckConstraint(
            "status in ('active','accepted','revoked','expired')",
            name="ck_enterprise_client_invites_status",
        ),
        CheckConstraint("length(email_hash) = 64", name="ck_enterprise_client_invites_email_hash"),
        CheckConstraint("length(token_hash) = 64", name="ck_enterprise_client_invites_token_hash"),
        CheckConstraint("version >= 1", name="ck_enterprise_client_invites_version"),
        CheckConstraint("expires_at > created_at", name="ck_enterprise_client_invites_expiry"),
        Index("ix_enterprise_client_invites_org_status", "organization_id", "status"),
        Index("ix_enterprise_client_invites_expires", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    location_group_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    email_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    encrypted_email: Mapped[str] = mapped_column(Text, nullable=False)
    encryption_key_reference: Mapped[str] = mapped_column(String(255), nullable=False)
    encryption_key_version: Mapped[str] = mapped_column(String(40), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    version: Mapped[int] = mapped_column(nullable=False, default=1)
    created_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    accepted_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

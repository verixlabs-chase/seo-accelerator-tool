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
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PortfolioLocationGroup(Base):
    __tablename__ = "portfolio_location_groups"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "name",
            name="uq_portfolio_location_groups_org_name",
        ),
        UniqueConstraint(
            "id",
            "organization_id",
            name="uq_portfolio_location_groups_id_org",
        ),
        Index(
            "ix_portfolio_location_groups_org_status",
            "organization_id",
            "status",
        ),
        CheckConstraint(
            "status in ('active','archived')",
            name="ck_portfolio_location_groups_status",
        ),
        CheckConstraint("version >= 1", name="ck_portfolio_location_groups_version"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="active")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class PortfolioLocationGroupMember(Base):
    __tablename__ = "portfolio_location_group_members"
    __table_args__ = (
        UniqueConstraint(
            "location_group_id",
            "business_location_id",
            name="uq_portfolio_location_group_members_group_location",
        ),
        Index(
            "ix_portfolio_location_group_members_org_group",
            "organization_id",
            "location_group_id",
        ),
        ForeignKeyConstraint(
            ["location_group_id", "organization_id"],
            ["portfolio_location_groups.id", "portfolio_location_groups.organization_id"],
            ondelete="CASCADE",
            name="fk_portfolio_location_group_members_group_org",
        ),
        ForeignKeyConstraint(
            ["business_location_id", "organization_id"],
            ["business_locations.id", "business_locations.organization_id"],
            ondelete="CASCADE",
            name="fk_portfolio_location_group_members_location_org",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    location_group_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True,
    )
    business_location_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True,
    )
    added_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )


class PortfolioLocationAccessGrant(Base):
    """Delegated portfolio authority limited to one saved location group."""

    __tablename__ = "portfolio_location_access_grants"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "user_id",
            "location_group_id",
            name="uq_portfolio_access_grants_org_user_group",
        ),
        Index(
            "ix_portfolio_access_grants_org_status",
            "organization_id",
            "status",
        ),
        Index(
            "ix_portfolio_access_grants_user_status",
            "user_id",
            "status",
        ),
        ForeignKeyConstraint(
            ["location_group_id", "organization_id"],
            ["portfolio_location_groups.id", "portfolio_location_groups.organization_id"],
            ondelete="CASCADE",
            name="fk_portfolio_access_grants_group_org",
        ),
        ForeignKeyConstraint(
            ["user_id", "organization_id"],
            ["organization_memberships.user_id", "organization_memberships.organization_id"],
            ondelete="CASCADE",
            name="fk_portfolio_access_grants_membership",
        ),
        CheckConstraint(
            "access_role in ('viewer','operator','approver')",
            name="ck_portfolio_access_grants_role",
        ),
        CheckConstraint(
            "status in ('active','revoked')",
            name="ck_portfolio_access_grants_status",
        ),
        CheckConstraint("version >= 1", name="ck_portfolio_access_grants_version"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    location_group_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    access_role: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="active")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    revoked_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PortfolioTargetSnapshot(Base):
    __tablename__ = "portfolio_target_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "request_key",
            name="uq_portfolio_target_snapshots_org_request_key",
        ),
        Index(
            "ix_portfolio_target_snapshots_org_created",
            "organization_id",
            "created_at",
        ),
        Index(
            "ix_portfolio_target_snapshots_group_created",
            "location_group_id",
            "created_at",
        ),
        ForeignKeyConstraint(
            ["location_group_id", "organization_id"],
            ["portfolio_location_groups.id", "portfolio_location_groups.organization_id"],
            name="fk_portfolio_target_snapshots_group_org",
        ),
        CheckConstraint(
            "selection_mode in ('group','all_active','explicit')",
            name="ck_portfolio_target_snapshots_selection_mode",
        ),
        CheckConstraint("target_count >= 0", name="ck_portfolio_target_snapshots_target_count"),
        CheckConstraint("blocked_count >= 0", name="ck_portfolio_target_snapshots_blocked_count"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    location_group_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        index=True,
    )
    location_group_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    action_key: Mapped[str] = mapped_column(String(80), nullable=False)
    request_key: Mapped[str] = mapped_column(String(120), nullable=False)
    selection_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    selection_json: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False, default=dict
    )
    targets_json: Mapped[list] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False, default=list
    )
    exceptions_json: Mapped[list] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False, default=list
    )
    target_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    blocked_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

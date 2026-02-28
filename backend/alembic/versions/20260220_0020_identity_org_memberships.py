"""identity and organization membership foundation

Revision ID: 20260220_0020
Revises: 20260219_0019
Create Date: 2026-02-20 00:10:00
"""

from __future__ import annotations

from alembic import context
from alembic import op
import sqlalchemy as sa


revision = "20260220_0020"
down_revision = "20260219_0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    offline = context.is_offline_mode()
    inspector = None if offline else sa.inspect(bind)

    if offline:
        op.add_column("users", sa.Column("is_platform_user", sa.Boolean(), nullable=False, server_default=sa.false()))
        op.add_column("users", sa.Column("platform_role", sa.String(length=30), nullable=True))
        op.create_index("ix_users_email", "users", ["email"])
        op.create_table(
            "organization_memberships",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column(
                "organization_id",
                sa.String(length=36),
                sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("role", sa.String(length=20), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("user_id", "organization_id", name="uq_org_membership_user_org"),
        )
        op.create_index("ix_organization_memberships_user_id", "organization_memberships", ["user_id"])
        op.create_index("ix_organization_memberships_organization_id", "organization_memberships", ["organization_id"])
        return

    user_columns = {column["name"] for column in inspector.get_columns("users")}
    if "is_platform_user" not in user_columns:
        op.add_column("users", sa.Column("is_platform_user", sa.Boolean(), nullable=False, server_default=sa.false()))
    if "platform_role" not in user_columns:
        op.add_column("users", sa.Column("platform_role", sa.String(length=30), nullable=True))

    user_indexes = {index["name"] for index in inspector.get_indexes("users")}
    if "ix_users_email" not in user_indexes:
        op.create_index("ix_users_email", "users", ["email"])

    tables = set(inspector.get_table_names())
    if "organization_memberships" not in tables:
        op.create_table(
            "organization_memberships",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column(
                "organization_id",
                sa.String(length=36),
                sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("role", sa.String(length=20), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("user_id", "organization_id", name="uq_org_membership_user_org"),
        )

    org_membership_indexes = {index["name"] for index in inspector.get_indexes("organization_memberships")}
    if "ix_organization_memberships_user_id" not in org_membership_indexes:
        op.create_index("ix_organization_memberships_user_id", "organization_memberships", ["user_id"])
    if "ix_organization_memberships_organization_id" not in org_membership_indexes:
        op.create_index("ix_organization_memberships_organization_id", "organization_memberships", ["organization_id"])


def downgrade() -> None:
    bind = op.get_bind()
    offline = context.is_offline_mode()
    inspector = None if offline else sa.inspect(bind)

    if offline:
        op.drop_index("ix_organization_memberships_organization_id", table_name="organization_memberships")
        op.drop_index("ix_organization_memberships_user_id", table_name="organization_memberships")
        op.drop_table("organization_memberships")
        op.drop_index("ix_users_email", table_name="users")
        op.drop_column("users", "platform_role")
        op.drop_column("users", "is_platform_user")
        return

    tables = set(inspector.get_table_names())
    if "organization_memberships" in tables:
        indexes = {index["name"] for index in inspector.get_indexes("organization_memberships")}
        if "ix_organization_memberships_organization_id" in indexes:
            op.drop_index("ix_organization_memberships_organization_id", table_name="organization_memberships")
        if "ix_organization_memberships_user_id" in indexes:
            op.drop_index("ix_organization_memberships_user_id", table_name="organization_memberships")
        op.drop_table("organization_memberships")

    indexes = {index["name"] for index in inspector.get_indexes("users")}
    if "ix_users_email" in indexes:
        op.drop_index("ix_users_email", table_name="users")

    columns = {column["name"] for column in inspector.get_columns("users")}
    if "platform_role" in columns:
        op.drop_column("users", "platform_role")
    if "is_platform_user" in columns:
        op.drop_column("users", "is_platform_user")

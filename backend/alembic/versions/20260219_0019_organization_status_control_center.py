"""add organization status for platform control center

Revision ID: 20260219_0019
Revises: 20260219_0018
Create Date: 2026-02-19 21:15:00
"""

from __future__ import annotations

from alembic import context
from alembic import op
import sqlalchemy as sa


revision = "20260219_0019"
down_revision = "20260219_0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    offline = context.is_offline_mode()
    inspector = None if offline else sa.inspect(bind)

    if offline:
        op.add_column(
            "organizations",
            sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        )
        op.create_index("ix_organizations_status", "organizations", ["status"])
        return

    column_names = {column["name"] for column in inspector.get_columns("organizations")}
    if "status" not in column_names:
        op.add_column(
            "organizations",
            sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        )

    existing_indexes = {index["name"] for index in inspector.get_indexes("organizations")}
    if "ix_organizations_status" not in existing_indexes:
        op.create_index("ix_organizations_status", "organizations", ["status"])


def downgrade() -> None:
    bind = op.get_bind()
    offline = context.is_offline_mode()
    inspector = None if offline else sa.inspect(bind)

    if offline:
        op.drop_index("ix_organizations_status", table_name="organizations")
        op.drop_column("organizations", "status")
        return

    existing_indexes = {index["name"] for index in inspector.get_indexes("organizations")}
    if "ix_organizations_status" in existing_indexes:
        op.drop_index("ix_organizations_status", table_name="organizations")

    column_names = {column["name"] for column in inspector.get_columns("organizations")}
    if "status" in column_names:
        op.drop_column("organizations", "status")

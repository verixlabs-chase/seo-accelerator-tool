"""add tenant-scoped automated data connections

Revision ID: 20260729_0075
Revises: 20260729_0074
Create Date: 2026-07-29 15:10:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260729_0075"
down_revision = "20260729_0074"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "data_connections",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("business_location_id", sa.String(length=36), nullable=False),
        sa.Column("campaign_id", sa.String(length=36), nullable=False),
        sa.Column("provider_name", sa.String(length=80), nullable=False),
        sa.Column("external_resource_id", sa.String(length=500), nullable=False),
        sa.Column("external_resource_name", sa.String(length=500), nullable=True),
        sa.Column("resource_scope", sa.String(length=40), nullable=False, server_default="property"),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="connected"),
        sa.Column("last_sync_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sync_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=120), nullable=True),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.Column("sync_cursor", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("connection_metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["business_location_id"], ["business_locations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "provider_name",
            "campaign_id",
            name="uq_data_connections_org_provider_campaign",
        ),
    )
    op.create_index(
        "ix_data_connections_tenant_id",
        "data_connections",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_data_connections_organization_id",
        "data_connections",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_data_connections_business_location_id",
        "data_connections",
        ["business_location_id"],
        unique=False,
    )
    op.create_index(
        "ix_data_connections_campaign_id",
        "data_connections",
        ["campaign_id"],
        unique=False,
    )
    op.create_index(
        "ix_data_connections_status",
        "data_connections",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_data_connections_due_sync",
        "data_connections",
        ["status", "next_sync_at"],
        unique=False,
    )
    op.create_index(
        "ix_data_connections_org_provider",
        "data_connections",
        ["organization_id", "provider_name"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_data_connections_org_provider", table_name="data_connections")
    op.drop_index("ix_data_connections_due_sync", table_name="data_connections")
    op.drop_index("ix_data_connections_status", table_name="data_connections")
    op.drop_index("ix_data_connections_campaign_id", table_name="data_connections")
    op.drop_index("ix_data_connections_business_location_id", table_name="data_connections")
    op.drop_index("ix_data_connections_organization_id", table_name="data_connections")
    op.drop_index("ix_data_connections_tenant_id", table_name="data_connections")
    op.drop_table("data_connections")

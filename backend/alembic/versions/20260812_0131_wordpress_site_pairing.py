"""add campaign-scoped WordPress site pairing

Revision ID: 20260812_0131
Revises: 20260812_0130
Create Date: 2026-08-12 23:59:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260812_0131"
down_revision = "20260812_0130"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "wordpress_site_connections",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("campaign_id", sa.String(36), nullable=False),
        sa.Column("site_url", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("pairing_code_hash", sa.String(64), nullable=True),
        sa.Column("pairing_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("encrypted_secret_blob", sa.Text(), nullable=True),
        sa.Column("key_reference", sa.String(120), nullable=True),
        sa.Column("key_version", sa.String(40), nullable=True),
        sa.Column("plugin_version", sa.String(40), nullable=True),
        sa.Column("paired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("disconnected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status in ('pending','connected','disconnected')",
            name="ck_wordpress_site_connections_status",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "campaign_id", name="uq_wordpress_site_connections_campaign"
        ),
        sa.UniqueConstraint(
            "pairing_code_hash", name="uq_wordpress_site_connections_pairing_hash"
        ),
    )
    for column in ("tenant_id", "organization_id", "campaign_id", "status"):
        op.create_index(
            f"ix_wordpress_site_connections_{column}",
            "wordpress_site_connections",
            [column],
        )
    op.create_index(
        "ix_wordpress_site_connections_org_status",
        "wordpress_site_connections",
        ["organization_id", "status"],
    )


def downgrade() -> None:
    op.drop_table("wordpress_site_connections")

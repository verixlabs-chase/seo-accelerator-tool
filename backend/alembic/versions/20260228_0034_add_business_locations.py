"""add business locations

Revision ID: 20260228_0034
Revises: 20260227_0033
Create Date: 2026-02-28 14:35:00
"""

from __future__ import annotations

from alembic import context
from alembic import op
import sqlalchemy as sa


revision = "20260228_0034"
down_revision = "20260227_0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    offline = context.is_offline_mode()
    _ = offline

    op.create_table(
        "business_locations",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column(
            "organization_id",
            sa.String(length=36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("domain", sa.String(length=255), nullable=True),
        sa.Column("primary_city", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "name", name="uq_business_locations_org_name"),
    )
    op.create_index(
        "ix_business_locations_organization_id",
        "business_locations",
        ["organization_id"],
        unique=False,
    )


def downgrade() -> None:
    offline = context.is_offline_mode()
    _ = offline

    op.drop_index("ix_business_locations_organization_id", table_name="business_locations")
    op.drop_table("business_locations")

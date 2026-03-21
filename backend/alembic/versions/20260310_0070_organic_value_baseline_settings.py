"""add organic value baseline settings

Revision ID: 20260310_0070
Revises: 20260310_0069
Create Date: 2026-03-10 10:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260310_0070"
down_revision = "20260310_0069"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "organic_value_baseline_settings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("campaign_id", sa.String(length=36), nullable=False),
        sa.Column("monthly_seo_investment", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("monthly_seo_investment_status", sa.String(length=24), nullable=False, server_default="unavailable"),
        sa.Column("monthly_seo_investment_source_type", sa.String(length=24), nullable=False, server_default="unavailable"),
        sa.Column("updated_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("monthly_seo_investment_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("campaign_id", name="uq_organic_value_baseline_settings_campaign_id"),
    )
    op.create_index(
        op.f("ix_organic_value_baseline_settings_campaign_id"),
        "organic_value_baseline_settings",
        ["campaign_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_organic_value_baseline_settings_campaign_id"), table_name="organic_value_baseline_settings")
    op.drop_table("organic_value_baseline_settings")

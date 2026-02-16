"""sprint4 competitor foundation tables

Revision ID: 20260216_0004
Revises: 20260216_0003
Create Date: 2026-02-16 15:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = "20260216_0004"
down_revision = "20260216_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "competitors",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("campaign_id", sa.String(length=36), sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("domain", sa.String(length=320), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_competitors_tenant_id", "competitors", ["tenant_id"])
    op.create_index("ix_competitors_campaign_id", "competitors", ["campaign_id"])

    op.create_table(
        "competitor_rankings",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("campaign_id", sa.String(length=36), nullable=False),
        sa.Column("competitor_id", sa.String(length=36), sa.ForeignKey("competitors.id", ondelete="CASCADE"), nullable=False),
        sa.Column("keyword", sa.String(length=255), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_competitor_rankings_tenant_id", "competitor_rankings", ["tenant_id"])
    op.create_index("ix_competitor_rankings_campaign_id", "competitor_rankings", ["campaign_id"])
    op.create_index("ix_competitor_rankings_competitor_id", "competitor_rankings", ["competitor_id"])
    op.create_index("ix_competitor_rankings_captured_at", "competitor_rankings", ["captured_at"])

    op.create_table(
        "competitor_pages",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("campaign_id", sa.String(length=36), nullable=False),
        sa.Column("competitor_id", sa.String(length=36), sa.ForeignKey("competitors.id", ondelete="CASCADE"), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("visibility_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_competitor_pages_tenant_id", "competitor_pages", ["tenant_id"])
    op.create_index("ix_competitor_pages_campaign_id", "competitor_pages", ["campaign_id"])
    op.create_index("ix_competitor_pages_competitor_id", "competitor_pages", ["competitor_id"])
    op.create_index("ix_competitor_pages_captured_at", "competitor_pages", ["captured_at"])

    op.create_table(
        "competitor_signals",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("campaign_id", sa.String(length=36), nullable=False),
        sa.Column("competitor_id", sa.String(length=36), sa.ForeignKey("competitors.id", ondelete="CASCADE"), nullable=False),
        sa.Column("signal_key", sa.String(length=120), nullable=False),
        sa.Column("signal_value", sa.String(length=255), nullable=False),
        sa.Column("score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_competitor_signals_tenant_id", "competitor_signals", ["tenant_id"])
    op.create_index("ix_competitor_signals_campaign_id", "competitor_signals", ["campaign_id"])
    op.create_index("ix_competitor_signals_competitor_id", "competitor_signals", ["competitor_id"])
    op.create_index("ix_competitor_signals_captured_at", "competitor_signals", ["captured_at"])


def downgrade() -> None:
    op.drop_index("ix_competitor_signals_captured_at", table_name="competitor_signals")
    op.drop_index("ix_competitor_signals_competitor_id", table_name="competitor_signals")
    op.drop_index("ix_competitor_signals_campaign_id", table_name="competitor_signals")
    op.drop_index("ix_competitor_signals_tenant_id", table_name="competitor_signals")
    op.drop_table("competitor_signals")

    op.drop_index("ix_competitor_pages_captured_at", table_name="competitor_pages")
    op.drop_index("ix_competitor_pages_competitor_id", table_name="competitor_pages")
    op.drop_index("ix_competitor_pages_campaign_id", table_name="competitor_pages")
    op.drop_index("ix_competitor_pages_tenant_id", table_name="competitor_pages")
    op.drop_table("competitor_pages")

    op.drop_index("ix_competitor_rankings_captured_at", table_name="competitor_rankings")
    op.drop_index("ix_competitor_rankings_competitor_id", table_name="competitor_rankings")
    op.drop_index("ix_competitor_rankings_campaign_id", table_name="competitor_rankings")
    op.drop_index("ix_competitor_rankings_tenant_id", table_name="competitor_rankings")
    op.drop_table("competitor_rankings")

    op.drop_index("ix_competitors_campaign_id", table_name="competitors")
    op.drop_index("ix_competitors_tenant_id", table_name="competitors")
    op.drop_table("competitors")


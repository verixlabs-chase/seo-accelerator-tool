"""sprint3 rank tracking foundation tables

Revision ID: 20260216_0003
Revises: 20260216_0002
Create Date: 2026-02-16 14:05:00
"""
from alembic import op
import sqlalchemy as sa


revision = "20260216_0003"
down_revision = "20260216_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "keyword_clusters",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("campaign_id", sa.String(length=36), sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_keyword_clusters_tenant_id", "keyword_clusters", ["tenant_id"])
    op.create_index("ix_keyword_clusters_campaign_id", "keyword_clusters", ["campaign_id"])

    op.create_table(
        "campaign_keywords",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("campaign_id", sa.String(length=36), sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cluster_id", sa.String(length=36), sa.ForeignKey("keyword_clusters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("keyword", sa.String(length=255), nullable=False),
        sa.Column("location_code", sa.String(length=64), nullable=False, server_default="US"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_campaign_keywords_tenant_id", "campaign_keywords", ["tenant_id"])
    op.create_index("ix_campaign_keywords_campaign_id", "campaign_keywords", ["campaign_id"])
    op.create_index("ix_campaign_keywords_cluster_id", "campaign_keywords", ["cluster_id"])

    op.create_table(
        "rankings",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("campaign_id", sa.String(length=36), nullable=False),
        sa.Column("keyword_id", sa.String(length=36), sa.ForeignKey("campaign_keywords.id", ondelete="CASCADE"), nullable=False),
        sa.Column("current_position", sa.Integer(), nullable=False),
        sa.Column("previous_position", sa.Integer(), nullable=True),
        sa.Column("delta", sa.Integer(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.8"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_rankings_tenant_id", "rankings", ["tenant_id"])
    op.create_index("ix_rankings_campaign_id", "rankings", ["campaign_id"])
    op.create_index("ix_rankings_keyword_id", "rankings", ["keyword_id"])

    op.create_table(
        "ranking_snapshots",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("campaign_id", sa.String(length=36), nullable=False),
        sa.Column("keyword_id", sa.String(length=36), sa.ForeignKey("campaign_keywords.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.8"),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("month_partition", sa.String(length=7), nullable=False),
    )
    op.create_index("ix_ranking_snapshots_tenant_id", "ranking_snapshots", ["tenant_id"])
    op.create_index("ix_ranking_snapshots_campaign_id", "ranking_snapshots", ["campaign_id"])
    op.create_index("ix_ranking_snapshots_keyword_id", "ranking_snapshots", ["keyword_id"])
    op.create_index("ix_ranking_snapshots_captured_at", "ranking_snapshots", ["captured_at"])
    op.create_index("ix_ranking_snapshots_month_partition", "ranking_snapshots", ["month_partition"])


def downgrade() -> None:
    op.drop_index("ix_ranking_snapshots_month_partition", table_name="ranking_snapshots")
    op.drop_index("ix_ranking_snapshots_captured_at", table_name="ranking_snapshots")
    op.drop_index("ix_ranking_snapshots_keyword_id", table_name="ranking_snapshots")
    op.drop_index("ix_ranking_snapshots_campaign_id", table_name="ranking_snapshots")
    op.drop_index("ix_ranking_snapshots_tenant_id", table_name="ranking_snapshots")
    op.drop_table("ranking_snapshots")

    op.drop_index("ix_rankings_keyword_id", table_name="rankings")
    op.drop_index("ix_rankings_campaign_id", table_name="rankings")
    op.drop_index("ix_rankings_tenant_id", table_name="rankings")
    op.drop_table("rankings")

    op.drop_index("ix_campaign_keywords_cluster_id", table_name="campaign_keywords")
    op.drop_index("ix_campaign_keywords_campaign_id", table_name="campaign_keywords")
    op.drop_index("ix_campaign_keywords_tenant_id", table_name="campaign_keywords")
    op.drop_table("campaign_keywords")

    op.drop_index("ix_keyword_clusters_campaign_id", table_name="keyword_clusters")
    op.drop_index("ix_keyword_clusters_tenant_id", table_name="keyword_clusters")
    op.drop_table("keyword_clusters")


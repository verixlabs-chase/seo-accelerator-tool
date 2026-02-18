"""add entity dominance foundation tables

Revision ID: 20260218_0015
Revises: 20260218_0014
Create Date: 2026-02-18 23:05:00
"""
from alembic import op
import sqlalchemy as sa


revision = "20260218_0015"
down_revision = "20260218_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "page_entities",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("campaign_id", sa.String(length=36), nullable=False),
        sa.Column("page_id", sa.String(length=36), sa.ForeignKey("pages.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "crawl_page_result_id",
            sa.String(length=36),
            sa.ForeignKey("crawl_page_results.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("entity", sa.String(length=120), nullable=False),
        sa.Column("source_type", sa.String(length=30), nullable=False, server_default="page"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("crawl_page_result_id", "entity", name="uq_page_entities_result_entity"),
    )
    op.create_index("ix_page_entities_tenant_id", "page_entities", ["tenant_id"])
    op.create_index("ix_page_entities_campaign_id", "page_entities", ["campaign_id"])
    op.create_index("ix_page_entities_page_id", "page_entities", ["page_id"])
    op.create_index("ix_page_entities_crawl_page_result_id", "page_entities", ["crawl_page_result_id"])
    op.create_index("ix_page_entities_entity", "page_entities", ["entity"])
    op.create_index("ix_page_entities_created_at", "page_entities", ["created_at"])

    op.create_table(
        "competitor_entities",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("campaign_id", sa.String(length=36), nullable=False),
        sa.Column("competitor_id", sa.String(length=36), sa.ForeignKey("competitors.id", ondelete="CASCADE"), nullable=False),
        sa.Column("competitor_page_id", sa.String(length=36), sa.ForeignKey("competitor_pages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entity", sa.String(length=120), nullable=False),
        sa.Column("source_type", sa.String(length=30), nullable=False, server_default="serp_snapshot"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("competitor_page_id", "entity", name="uq_competitor_entities_page_entity"),
    )
    op.create_index("ix_competitor_entities_tenant_id", "competitor_entities", ["tenant_id"])
    op.create_index("ix_competitor_entities_campaign_id", "competitor_entities", ["campaign_id"])
    op.create_index("ix_competitor_entities_competitor_id", "competitor_entities", ["competitor_id"])
    op.create_index("ix_competitor_entities_competitor_page_id", "competitor_entities", ["competitor_page_id"])
    op.create_index("ix_competitor_entities_entity", "competitor_entities", ["entity"])
    op.create_index("ix_competitor_entities_created_at", "competitor_entities", ["created_at"])

    op.create_table(
        "entity_analysis_runs",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("campaign_id", sa.String(length=36), nullable=False),
        sa.Column("entity_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("overlap_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("campaign_entity_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("competitor_entity_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("missing_entities_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("confidence_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("evidence_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("recommendations_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_entity_analysis_runs_tenant_id", "entity_analysis_runs", ["tenant_id"])
    op.create_index("ix_entity_analysis_runs_campaign_id", "entity_analysis_runs", ["campaign_id"])
    op.create_index("ix_entity_analysis_runs_created_at", "entity_analysis_runs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_entity_analysis_runs_created_at", table_name="entity_analysis_runs")
    op.drop_index("ix_entity_analysis_runs_campaign_id", table_name="entity_analysis_runs")
    op.drop_index("ix_entity_analysis_runs_tenant_id", table_name="entity_analysis_runs")
    op.drop_table("entity_analysis_runs")

    op.drop_index("ix_competitor_entities_created_at", table_name="competitor_entities")
    op.drop_index("ix_competitor_entities_entity", table_name="competitor_entities")
    op.drop_index("ix_competitor_entities_competitor_page_id", table_name="competitor_entities")
    op.drop_index("ix_competitor_entities_competitor_id", table_name="competitor_entities")
    op.drop_index("ix_competitor_entities_campaign_id", table_name="competitor_entities")
    op.drop_index("ix_competitor_entities_tenant_id", table_name="competitor_entities")
    op.drop_table("competitor_entities")

    op.drop_index("ix_page_entities_created_at", table_name="page_entities")
    op.drop_index("ix_page_entities_entity", table_name="page_entities")
    op.drop_index("ix_page_entities_crawl_page_result_id", table_name="page_entities")
    op.drop_index("ix_page_entities_page_id", table_name="page_entities")
    op.drop_index("ix_page_entities_campaign_id", table_name="page_entities")
    op.drop_index("ix_page_entities_tenant_id", table_name="page_entities")
    op.drop_table("page_entities")

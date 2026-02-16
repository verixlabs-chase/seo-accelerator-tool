"""sprint2 crawl foundation tables

Revision ID: 20260216_0002
Revises: 20260216_0001
Create Date: 2026-02-16 12:30:00
"""
from alembic import op
import sqlalchemy as sa


revision = "20260216_0002"
down_revision = "20260216_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pages",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("campaign_id", sa.String(length=36), sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("last_crawled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_pages_tenant_id", "pages", ["tenant_id"])
    op.create_index("ix_pages_campaign_id", "pages", ["campaign_id"])

    op.create_table(
        "crawl_runs",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("campaign_id", sa.String(length=36), sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("crawl_type", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("seed_url", sa.Text(), nullable=False),
        sa.Column("pages_discovered", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_crawl_runs_tenant_id", "crawl_runs", ["tenant_id"])
    op.create_index("ix_crawl_runs_campaign_id", "crawl_runs", ["campaign_id"])

    op.create_table(
        "crawl_page_results",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("campaign_id", sa.String(length=36), nullable=False),
        sa.Column("crawl_run_id", sa.String(length=36), sa.ForeignKey("crawl_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("page_id", sa.String(length=36), sa.ForeignKey("pages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("is_indexable", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("title", sa.String(length=320), nullable=True),
        sa.Column("crawled_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_crawl_page_results_tenant_id", "crawl_page_results", ["tenant_id"])
    op.create_index("ix_crawl_page_results_campaign_id", "crawl_page_results", ["campaign_id"])
    op.create_index("ix_crawl_page_results_crawl_run_id", "crawl_page_results", ["crawl_run_id"])
    op.create_index("ix_crawl_page_results_crawled_at", "crawl_page_results", ["crawled_at"])
    op.create_index(
        "ix_crawl_page_results_tenant_campaign_crawled",
        "crawl_page_results",
        ["tenant_id", "campaign_id", "crawled_at"],
    )

    op.create_table(
        "technical_issues",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("campaign_id", sa.String(length=36), nullable=False),
        sa.Column("crawl_run_id", sa.String(length=36), sa.ForeignKey("crawl_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("page_id", sa.String(length=36), sa.ForeignKey("pages.id", ondelete="SET NULL"), nullable=True),
        sa.Column("issue_code", sa.String(length=120), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("details_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_technical_issues_tenant_id", "technical_issues", ["tenant_id"])
    op.create_index("ix_technical_issues_campaign_id", "technical_issues", ["campaign_id"])
    op.create_index("ix_technical_issues_crawl_run_id", "technical_issues", ["crawl_run_id"])
    op.create_index("ix_technical_issues_detected_at", "technical_issues", ["detected_at"])


def downgrade() -> None:
    op.drop_index("ix_technical_issues_detected_at", table_name="technical_issues")
    op.drop_index("ix_technical_issues_crawl_run_id", table_name="technical_issues")
    op.drop_index("ix_technical_issues_campaign_id", table_name="technical_issues")
    op.drop_index("ix_technical_issues_tenant_id", table_name="technical_issues")
    op.drop_table("technical_issues")

    op.drop_index("ix_crawl_page_results_tenant_campaign_crawled", table_name="crawl_page_results")
    op.drop_index("ix_crawl_page_results_crawled_at", table_name="crawl_page_results")
    op.drop_index("ix_crawl_page_results_crawl_run_id", table_name="crawl_page_results")
    op.drop_index("ix_crawl_page_results_campaign_id", table_name="crawl_page_results")
    op.drop_index("ix_crawl_page_results_tenant_id", table_name="crawl_page_results")
    op.drop_table("crawl_page_results")

    op.drop_index("ix_crawl_runs_campaign_id", table_name="crawl_runs")
    op.drop_index("ix_crawl_runs_tenant_id", table_name="crawl_runs")
    op.drop_table("crawl_runs")

    op.drop_index("ix_pages_campaign_id", table_name="pages")
    op.drop_index("ix_pages_tenant_id", table_name="pages")
    op.drop_table("pages")


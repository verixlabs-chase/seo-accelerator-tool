"""add crawl frontier queue table

Revision ID: 20260217_0010
Revises: 20260216_0009
Create Date: 2026-02-17 15:50:00
"""
from alembic import op
import sqlalchemy as sa


revision = "20260217_0010"
down_revision = "20260216_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "crawl_frontier_urls",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("campaign_id", sa.String(length=36), nullable=False),
        sa.Column("crawl_run_id", sa.String(length=36), sa.ForeignKey("crawl_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("normalized_url", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("depth", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("discovered_from_url", sa.Text(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("crawl_run_id", "normalized_url", name="uq_crawl_frontier_run_normalized_url"),
    )
    op.create_index("ix_crawl_frontier_urls_tenant_id", "crawl_frontier_urls", ["tenant_id"])
    op.create_index("ix_crawl_frontier_urls_campaign_id", "crawl_frontier_urls", ["campaign_id"])
    op.create_index("ix_crawl_frontier_urls_crawl_run_id", "crawl_frontier_urls", ["crawl_run_id"])
    op.create_index("ix_crawl_frontier_urls_status", "crawl_frontier_urls", ["status"])
    op.create_index("ix_crawl_frontier_urls_created_at", "crawl_frontier_urls", ["created_at"])
    op.create_index(
        "ix_crawl_frontier_urls_run_status_created",
        "crawl_frontier_urls",
        ["crawl_run_id", "status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_crawl_frontier_urls_run_status_created", table_name="crawl_frontier_urls")
    op.drop_index("ix_crawl_frontier_urls_created_at", table_name="crawl_frontier_urls")
    op.drop_index("ix_crawl_frontier_urls_status", table_name="crawl_frontier_urls")
    op.drop_index("ix_crawl_frontier_urls_crawl_run_id", table_name="crawl_frontier_urls")
    op.drop_index("ix_crawl_frontier_urls_campaign_id", table_name="crawl_frontier_urls")
    op.drop_index("ix_crawl_frontier_urls_tenant_id", table_name="crawl_frontier_urls")
    op.drop_table("crawl_frontier_urls")

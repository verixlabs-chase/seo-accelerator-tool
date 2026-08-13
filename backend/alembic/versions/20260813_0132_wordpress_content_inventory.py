"""add read-only WordPress content inventory

Revision ID: 20260813_0132
Revises: 20260812_0131
Create Date: 2026-08-13 00:01:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260813_0132"
down_revision = "20260812_0131"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "wordpress_content_sync_runs",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("campaign_id", sa.String(36), nullable=False),
        sa.Column("wordpress_site_connection_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("item_count", sa.Integer(), nullable=False),
        sa.Column("source_total_count", sa.Integer(), nullable=False),
        sa.Column("truncated", sa.Boolean(), nullable=False),
        sa.Column("plugin_version", sa.String(40), nullable=True),
        sa.Column("wordpress_version", sa.String(40), nullable=True),
        sa.Column("php_version", sa.String(40), nullable=True),
        sa.Column("seo_plugins", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.String(80), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status in ('running','complete','failed')",
            name="ck_wordpress_content_sync_runs_status",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["wordpress_site_connection_id"],
            ["wordpress_site_connections.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in (
        "tenant_id",
        "organization_id",
        "campaign_id",
        "wordpress_site_connection_id",
        "status",
    ):
        op.create_index(
            f"ix_wordpress_content_sync_runs_{column}",
            "wordpress_content_sync_runs",
            [column],
        )
    op.create_index(
        "ix_wordpress_content_sync_runs_campaign_started",
        "wordpress_content_sync_runs",
        ["campaign_id", "started_at"],
    )

    op.create_table(
        "wordpress_content_items",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("campaign_id", sa.String(36), nullable=False),
        sa.Column("sync_run_id", sa.String(36), nullable=False),
        sa.Column("wp_post_id", sa.Integer(), nullable=False),
        sa.Column("post_type", sa.String(80), nullable=False),
        sa.Column("publication_status", sa.String(24), nullable=False),
        sa.Column("slug", sa.String(320), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("meta_title", sa.Text(), nullable=True),
        sa.Column("meta_description", sa.Text(), nullable=True),
        sa.Column("canonical_url", sa.Text(), nullable=True),
        sa.Column("headings", sa.JSON(), nullable=False),
        sa.Column("internal_links", sa.JSON(), nullable=False),
        sa.Column("schema_types", sa.JSON(), nullable=False),
        sa.Column("schema_present", sa.Boolean(), nullable=False),
        sa.Column("word_count", sa.Integer(), nullable=False),
        sa.Column("revision_id", sa.String(120), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("modified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["sync_run_id"], ["wordpress_content_sync_runs.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "sync_run_id", "wp_post_id", name="uq_wordpress_content_items_run_post"
        ),
    )
    for column in ("tenant_id", "organization_id", "campaign_id", "sync_run_id"):
        op.create_index(
            f"ix_wordpress_content_items_{column}",
            "wordpress_content_items",
            [column],
        )
    op.create_index(
        "ix_wordpress_content_items_campaign_url",
        "wordpress_content_items",
        ["campaign_id", "url"],
    )


def downgrade() -> None:
    op.drop_table("wordpress_content_items")
    op.drop_table("wordpress_content_sync_runs")

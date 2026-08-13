"""add owned-site index inspection and sitemap evidence

Revision ID: 20260813_0147
Revises: 20260813_0146
Create Date: 2026-08-13 23:55:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260813_0147"
down_revision = "20260813_0146"
branch_labels = None
depends_on = None


def _enable_rls(table_name: str) -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    expression = (
        "current_setting('app.platform_access', true) = 'on' OR ("
        "tenant_id::text = current_setting('app.current_tenant_id', true) AND "
        "organization_id::text = current_setting('app.current_organization_id', true))"
    )
    op.execute(
        sa.text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.{table_name} TO lsos_app")
    )
    op.execute(sa.text(f"ALTER TABLE public.{table_name} ENABLE ROW LEVEL SECURITY"))
    op.execute(
        sa.text(
            f"CREATE POLICY lsos_tenant_isolation ON public.{table_name} "
            f"FOR ALL TO lsos_app USING ({expression}) WITH CHECK ({expression})"
        )
    )


def upgrade() -> None:
    op.create_table(
        "url_inspection_snapshots",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("campaign_id", sa.String(36), nullable=False),
        sa.Column("connection_id", sa.String(36), nullable=False),
        sa.Column("page_id", sa.String(36), nullable=True),
        sa.Column("site_url", sa.Text(), nullable=False),
        sa.Column("inspection_url", sa.Text(), nullable=False),
        sa.Column("verdict", sa.String(40), nullable=False),
        sa.Column("coverage_state", sa.String(240), nullable=True),
        sa.Column("robots_txt_state", sa.String(60), nullable=True),
        sa.Column("indexing_state", sa.String(60), nullable=True),
        sa.Column("page_fetch_state", sa.String(80), nullable=True),
        sa.Column("google_canonical", sa.Text(), nullable=True),
        sa.Column("user_canonical", sa.Text(), nullable=True),
        sa.Column("crawled_as", sa.String(60), nullable=True),
        sa.Column("last_crawl_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sitemap_urls", sa.JSON(), nullable=False),
        sa.Column("referring_urls", sa.JSON(), nullable=False),
        sa.Column("source_contract_version", sa.String(60), nullable=False),
        sa.Column("inspected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["connection_id"], ["data_connections.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["page_id"], ["pages.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "campaign_id",
            "inspection_url",
            name="uq_url_inspection_snapshots_campaign_url",
        ),
    )
    op.create_index("ix_url_inspection_snapshots_tenant_id", "url_inspection_snapshots", ["tenant_id"])
    op.create_index("ix_url_inspection_snapshots_organization_id", "url_inspection_snapshots", ["organization_id"])
    op.create_index("ix_url_inspection_snapshots_campaign_id", "url_inspection_snapshots", ["campaign_id"])
    op.create_index("ix_url_inspection_snapshots_connection_id", "url_inspection_snapshots", ["connection_id"])
    op.create_index("ix_url_inspection_snapshots_page_id", "url_inspection_snapshots", ["page_id"])
    op.create_index("ix_url_inspection_snapshots_inspected_at", "url_inspection_snapshots", ["inspected_at"])
    op.create_index(
        "ix_url_inspection_snapshots_campaign_inspected",
        "url_inspection_snapshots",
        ["campaign_id", "inspected_at"],
    )

    op.create_table(
        "search_console_sitemap_snapshots",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("campaign_id", sa.String(36), nullable=False),
        sa.Column("connection_id", sa.String(36), nullable=False),
        sa.Column("site_url", sa.Text(), nullable=False),
        sa.Column("sitemap_url", sa.Text(), nullable=False),
        sa.Column("sitemap_type", sa.String(40), nullable=True),
        sa.Column("is_pending", sa.Boolean(), nullable=False),
        sa.Column("is_sitemaps_index", sa.Boolean(), nullable=False),
        sa.Column("warnings", sa.Integer(), nullable=False),
        sa.Column("errors", sa.Integer(), nullable=False),
        sa.Column("submitted_url_count", sa.Integer(), nullable=False),
        sa.Column("contents", sa.JSON(), nullable=False),
        sa.Column("last_submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_downloaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_contract_version", sa.String(60), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["connection_id"], ["data_connections.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "campaign_id",
            "sitemap_url",
            name="uq_search_console_sitemaps_campaign_url",
        ),
    )
    op.create_index("ix_search_console_sitemap_snapshots_tenant_id", "search_console_sitemap_snapshots", ["tenant_id"])
    op.create_index("ix_search_console_sitemap_snapshots_organization_id", "search_console_sitemap_snapshots", ["organization_id"])
    op.create_index("ix_search_console_sitemap_snapshots_campaign_id", "search_console_sitemap_snapshots", ["campaign_id"])
    op.create_index("ix_search_console_sitemap_snapshots_connection_id", "search_console_sitemap_snapshots", ["connection_id"])
    op.create_index("ix_search_console_sitemap_snapshots_observed_at", "search_console_sitemap_snapshots", ["observed_at"])
    op.create_index(
        "ix_search_console_sitemaps_campaign_observed",
        "search_console_sitemap_snapshots",
        ["campaign_id", "observed_at"],
    )

    _enable_rls("url_inspection_snapshots")
    _enable_rls("search_console_sitemap_snapshots")


def downgrade() -> None:
    for table_name in (
        "search_console_sitemap_snapshots",
        "url_inspection_snapshots",
    ):
        if op.get_bind().dialect.name == "postgresql":
            op.execute(
                sa.text(f"DROP POLICY IF EXISTS lsos_tenant_isolation ON public.{table_name}")
            )
            op.execute(sa.text(f"ALTER TABLE public.{table_name} DISABLE ROW LEVEL SECURITY"))
        op.drop_table(table_name)

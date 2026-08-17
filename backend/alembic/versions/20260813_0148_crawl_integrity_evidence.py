"""add crawl relationship and integrity evidence

Revision ID: 20260813_0148
Revises: 20260813_0147
Create Date: 2026-08-13 23:59:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260813_0148"
down_revision = "20260813_0147"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("crawl_page_results") as batch_op:
        batch_op.add_column(sa.Column("final_url", sa.Text(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "redirect_chain",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'[]'"),
            )
        )
        batch_op.add_column(
            sa.Column("redirect_count", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(sa.Column("canonical_url", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("content_hash", sa.String(64), nullable=True))
        batch_op.add_column(
            sa.Column("word_count", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(
            sa.Column("internal_link_count", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(
            sa.Column(
                "structured_data_types",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'[]'"),
            )
        )
        batch_op.add_column(
            sa.Column(
                "structured_data_valid",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            )
        )
        batch_op.create_index(
            "ix_crawl_page_results_content_hash",
            ["content_hash"],
            unique=False,
        )

    op.create_table(
        "crawl_internal_links",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("campaign_id", sa.String(36), nullable=False),
        sa.Column("crawl_run_id", sa.String(36), nullable=False),
        sa.Column("source_page_id", sa.String(36), nullable=False),
        sa.Column("target_page_id", sa.String(36), nullable=True),
        sa.Column("target_url", sa.Text(), nullable=False),
        sa.Column("normalized_target_url", sa.Text(), nullable=False),
        sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["crawl_run_id"], ["crawl_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_page_id"], ["pages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_page_id"], ["pages.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "crawl_run_id",
            "source_page_id",
            "normalized_target_url",
            name="uq_crawl_links_run_source_target",
        ),
    )
    op.create_index("ix_crawl_internal_links_tenant_id", "crawl_internal_links", ["tenant_id"])
    op.create_index(
        "ix_crawl_internal_links_campaign_id",
        "crawl_internal_links",
        ["campaign_id"],
    )
    op.create_index(
        "ix_crawl_internal_links_crawl_run_id",
        "crawl_internal_links",
        ["crawl_run_id"],
    )
    op.create_index(
        "ix_crawl_internal_links_source_page_id",
        "crawl_internal_links",
        ["source_page_id"],
    )
    op.create_index(
        "ix_crawl_internal_links_target_page_id",
        "crawl_internal_links",
        ["target_page_id"],
    )
    op.create_index(
        "ix_crawl_links_run_target",
        "crawl_internal_links",
        ["crawl_run_id", "normalized_target_url"],
    )

    if op.get_bind().dialect.name == "postgresql":
        expression = (
            "current_setting('app.platform_access', true) = 'on' OR "
            "tenant_id::text = current_setting('app.current_tenant_id', true)"
        )
        op.execute(
            sa.text(
                "GRANT SELECT, INSERT, UPDATE, DELETE "
                "ON TABLE public.crawl_internal_links TO lsos_app"
            )
        )
        op.execute(sa.text("ALTER TABLE public.crawl_internal_links ENABLE ROW LEVEL SECURITY"))
        op.execute(
            sa.text(
                "CREATE POLICY lsos_tenant_isolation ON public.crawl_internal_links "
                f"FOR ALL TO lsos_app USING ({expression}) WITH CHECK ({expression})"
            )
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            sa.text(
                "DROP POLICY IF EXISTS lsos_tenant_isolation "
                "ON public.crawl_internal_links"
            )
        )
        op.execute(sa.text("ALTER TABLE public.crawl_internal_links DISABLE ROW LEVEL SECURITY"))
    op.drop_table("crawl_internal_links")

    with op.batch_alter_table("crawl_page_results") as batch_op:
        batch_op.drop_index("ix_crawl_page_results_content_hash")
        batch_op.drop_column("structured_data_valid")
        batch_op.drop_column("structured_data_types")
        batch_op.drop_column("internal_link_count")
        batch_op.drop_column("word_count")
        batch_op.drop_column("content_hash")
        batch_op.drop_column("canonical_url")
        batch_op.drop_column("redirect_count")
        batch_op.drop_column("redirect_chain")
        batch_op.drop_column("final_url")

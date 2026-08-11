"""add official standards source registry and immutable snapshots

Revision ID: 20260805_0100
Revises: 20260805_0099
Create Date: 2026-08-05 16:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260805_0100"
down_revision = "20260805_0099"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "standards_source_registry",
        sa.Column("source_id", sa.String(length=120), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("source_owner", sa.String(length=120), nullable=False),
        sa.Column("source_uri", sa.Text(), nullable=False),
        sa.Column("source_format", sa.String(length=30), nullable=False),
        sa.Column("source_scope", sa.String(length=80), nullable=False),
        sa.Column("parser_version", sa.String(length=40), nullable=False),
        sa.Column("review_interval_hours", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_http_status", sa.Integer(), nullable=True),
        sa.Column("last_source_digest", sa.String(length=64), nullable=True),
        sa.Column("last_normalized_digest", sa.String(length=64), nullable=True),
        sa.Column("last_error_code", sa.String(length=80), nullable=True),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("source_id"),
    )
    op.create_index(
        "ix_standards_source_registry_source_scope",
        "standards_source_registry",
        ["source_scope"],
    )
    op.create_index(
        "ix_standards_source_registry_is_active",
        "standards_source_registry",
        ["is_active"],
    )
    op.create_index(
        "ix_standards_source_registry_updated_at",
        "standards_source_registry",
        ["updated_at"],
    )

    op.create_table(
        "standards_source_snapshots",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source_id", sa.String(length=120), nullable=False),
        sa.Column("source_uri", sa.Text(), nullable=False),
        sa.Column("source_format", sa.String(length=30), nullable=False),
        sa.Column("parser_version", sa.String(length=40), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=False),
        sa.Column("content_type", sa.String(length=200), nullable=True),
        sa.Column("etag", sa.Text(), nullable=True),
        sa.Column("last_modified", sa.Text(), nullable=True),
        sa.Column("source_digest", sa.String(length=64), nullable=False),
        sa.Column("normalized_digest", sa.String(length=64), nullable=False),
        sa.Column("content_bytes", sa.Integer(), nullable=False),
        sa.Column("content_text", sa.Text(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["standards_source_registry.source_id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_id",
            "source_digest",
            name="uq_standards_source_snapshot_digest",
        ),
    )
    op.create_index(
        "ix_standards_source_snapshots_source_id",
        "standards_source_snapshots",
        ["source_id"],
    )
    op.create_index(
        "ix_standards_source_snapshots_observed_at",
        "standards_source_snapshots",
        ["observed_at"],
    )
    op.create_index(
        "ix_standards_source_snapshots_source_observed",
        "standards_source_snapshots",
        ["source_id", "observed_at"],
    )

    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            sa.text(
                """
                CREATE OR REPLACE FUNCTION public.prevent_standards_snapshot_mutation()
                RETURNS trigger
                LANGUAGE plpgsql
                AS $$
                BEGIN
                    IF current_setting('app.platform_maintenance', true) IS DISTINCT FROM 'on'
                    THEN
                        RAISE EXCEPTION 'standards source snapshots are immutable';
                    END IF;
                    IF TG_OP = 'DELETE' THEN
                        RETURN OLD;
                    END IF;
                    RETURN NEW;
                END;
                $$;

                CREATE TRIGGER trg_standards_source_snapshots_immutable
                    BEFORE UPDATE OR DELETE ON public.standards_source_snapshots
                    FOR EACH ROW
                    EXECUTE FUNCTION public.prevent_standards_snapshot_mutation();
                """
            )
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            sa.text(
                """
                DROP TRIGGER IF EXISTS trg_standards_source_snapshots_immutable
                    ON public.standards_source_snapshots;
                DROP FUNCTION IF EXISTS public.prevent_standards_snapshot_mutation();
                """
            )
        )
    op.drop_index(
        "ix_standards_source_snapshots_source_observed",
        table_name="standards_source_snapshots",
    )
    op.drop_index(
        "ix_standards_source_snapshots_observed_at",
        table_name="standards_source_snapshots",
    )
    op.drop_index(
        "ix_standards_source_snapshots_source_id",
        table_name="standards_source_snapshots",
    )
    op.drop_table("standards_source_snapshots")
    op.drop_index(
        "ix_standards_source_registry_updated_at",
        table_name="standards_source_registry",
    )
    op.drop_index(
        "ix_standards_source_registry_is_active",
        table_name="standards_source_registry",
    )
    op.drop_index(
        "ix_standards_source_registry_source_scope",
        table_name="standards_source_registry",
    )
    op.drop_table("standards_source_registry")

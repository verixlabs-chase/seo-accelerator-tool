"""add tenant-scoped website performance measurements

Revision ID: 20260730_0079
Revises: 20260730_0078
Create Date: 2026-07-30 18:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260730_0079"
down_revision = "20260730_0078"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "website_performance_measurements",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("business_location_id", sa.String(length=36), nullable=True),
        sa.Column("campaign_id", sa.String(length=36), nullable=False),
        sa.Column("requested_url", sa.String(length=1000), nullable=False),
        sa.Column("measured_url", sa.String(length=1000), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("scope", sa.String(length=20), nullable=False, server_default="url"),
        sa.Column("form_factor", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("lcp_ms", sa.Float(), nullable=True),
        sa.Column("inp_ms", sa.Float(), nullable=True),
        sa.Column("cls_value", sa.Float(), nullable=True),
        sa.Column("ttfb_ms", sa.Float(), nullable=True),
        sa.Column("fcp_ms", sa.Float(), nullable=True),
        sa.Column("tbt_ms", sa.Float(), nullable=True),
        sa.Column("performance_score", sa.Float(), nullable=True),
        sa.Column("collection_start", sa.Date(), nullable=True),
        sa.Column("collection_end", sa.Date(), nullable=True),
        sa.Column("source_version", sa.String(length=120), nullable=True),
        sa.Column("lexicon_id", sa.String(length=120), nullable=False),
        sa.Column("lexicon_version", sa.String(length=80), nullable=False),
        sa.Column("fallback_to_origin", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("distribution", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("diagnostics", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("error_code", sa.String(length=120), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["business_location_id"],
            ["business_locations.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "idempotency_key",
            name="uq_website_performance_measurements_idempotency_key",
        ),
    )
    op.create_index(
        "ix_website_performance_measurements_tenant_id",
        "website_performance_measurements",
        ["tenant_id"],
    )
    op.create_index(
        "ix_website_performance_measurements_organization_id",
        "website_performance_measurements",
        ["organization_id"],
    )
    op.create_index(
        "ix_website_performance_measurements_business_location_id",
        "website_performance_measurements",
        ["business_location_id"],
    )
    op.create_index(
        "ix_website_performance_measurements_campaign_id",
        "website_performance_measurements",
        ["campaign_id"],
    )
    op.create_index(
        "ix_website_performance_measurements_source",
        "website_performance_measurements",
        ["source"],
    )
    op.create_index(
        "ix_website_performance_measurements_form_factor",
        "website_performance_measurements",
        ["form_factor"],
    )
    op.create_index(
        "ix_website_performance_measurements_status",
        "website_performance_measurements",
        ["status"],
    )
    op.create_index(
        "ix_website_performance_measurements_captured_at",
        "website_performance_measurements",
        ["captured_at"],
    )
    op.create_index(
        "ix_website_performance_campaign_history",
        "website_performance_measurements",
        ["campaign_id", "form_factor", "source", "captured_at"],
    )
    op.create_index(
        "ix_website_performance_tenant_status",
        "website_performance_measurements",
        ["tenant_id", "status", "captured_at"],
    )

    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            sa.text(
                """
                ALTER TABLE public.website_performance_measurements
                    ENABLE ROW LEVEL SECURITY;
                DROP POLICY IF EXISTS lsos_tenant_isolation
                    ON public.website_performance_measurements;
                CREATE POLICY lsos_tenant_isolation
                    ON public.website_performance_measurements
                    FOR ALL TO lsos_app
                    USING (
                        current_setting('app.platform_access', true) = 'on'
                        OR (
                            tenant_id::text =
                                current_setting('app.current_tenant_id', true)
                            AND organization_id::text =
                                current_setting('app.current_organization_id', true)
                        )
                    )
                    WITH CHECK (
                        current_setting('app.platform_access', true) = 'on'
                        OR (
                            tenant_id::text =
                                current_setting('app.current_tenant_id', true)
                            AND organization_id::text =
                                current_setting('app.current_organization_id', true)
                        )
                    );
                """
            )
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            sa.text(
                """
                DROP POLICY IF EXISTS lsos_tenant_isolation
                    ON public.website_performance_measurements;
                ALTER TABLE public.website_performance_measurements
                    DISABLE ROW LEVEL SECURITY;
                """
            )
        )
    op.drop_index(
        "ix_website_performance_tenant_status",
        table_name="website_performance_measurements",
    )
    op.drop_index(
        "ix_website_performance_campaign_history",
        table_name="website_performance_measurements",
    )
    op.drop_index(
        "ix_website_performance_measurements_captured_at",
        table_name="website_performance_measurements",
    )
    op.drop_index(
        "ix_website_performance_measurements_status",
        table_name="website_performance_measurements",
    )
    op.drop_index(
        "ix_website_performance_measurements_form_factor",
        table_name="website_performance_measurements",
    )
    op.drop_index(
        "ix_website_performance_measurements_source",
        table_name="website_performance_measurements",
    )
    op.drop_index(
        "ix_website_performance_measurements_campaign_id",
        table_name="website_performance_measurements",
    )
    op.drop_index(
        "ix_website_performance_measurements_business_location_id",
        table_name="website_performance_measurements",
    )
    op.drop_index(
        "ix_website_performance_measurements_organization_id",
        table_name="website_performance_measurements",
    )
    op.drop_index(
        "ix_website_performance_measurements_tenant_id",
        table_name="website_performance_measurements",
    )
    op.drop_table("website_performance_measurements")

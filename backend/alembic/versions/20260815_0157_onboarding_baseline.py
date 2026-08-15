"""add immutable onboarding baseline reports

Revision ID: 20260815_0157
Revises: 20260815_0156
Create Date: 2026-08-15 16:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260815_0157"
down_revision = "20260815_0156"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "onboarding_baselines",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("campaign_id", sa.String(length=36), nullable=False),
        sa.Column("business_location_id", sa.String(length=36), nullable=False),
        sa.Column("report_id", sa.String(length=36), nullable=False),
        sa.Column("generated_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("baseline_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("analysis_version", sa.String(length=40), nullable=False),
        sa.Column("evidence_window_days", sa.Integer(), nullable=False),
        sa.Column("window_start", sa.Date(), nullable=False),
        sa.Column("window_end", sa.Date(), nullable=False),
        sa.Column("cutoff_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_states", sa.JSON(), nullable=False),
        sa.Column("evidence_snapshot", sa.JSON(), nullable=False),
        sa.Column("score_snapshot", sa.JSON(), nullable=False),
        sa.Column("diagnosis_snapshot", sa.JSON(), nullable=False),
        sa.Column("report_snapshot_hash", sa.String(length=64), nullable=False),
        sa.Column("baseline_hash", sa.String(length=64), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status in ('ready','limited')",
            name="ck_onboarding_baselines_status",
        ),
        sa.CheckConstraint(
            "evidence_window_days = 28",
            name="ck_onboarding_baselines_window_days",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["generated_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["report_id"], ["monthly_reports.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["campaign_id", "tenant_id", "organization_id", "business_location_id"],
            [
                "campaigns.id",
                "campaigns.tenant_id",
                "campaigns.organization_id",
                "campaigns.business_location_id",
            ],
            name="fk_onboarding_baselines_campaign_scope",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "baseline_hash", name="uq_onboarding_baselines_hash"
        ),
        sa.UniqueConstraint(
            "campaign_id",
            "baseline_number",
            name="uq_onboarding_baselines_campaign_number",
        ),
        sa.UniqueConstraint("report_id"),
    )
    op.create_index(
        "ix_onboarding_baselines_tenant_id",
        "onboarding_baselines",
        ["tenant_id"],
    )
    op.create_index(
        "ix_onboarding_baselines_organization_id",
        "onboarding_baselines",
        ["organization_id"],
    )
    op.create_index(
        "ix_onboarding_baselines_campaign_id",
        "onboarding_baselines",
        ["campaign_id"],
    )
    op.create_index(
        "ix_onboarding_baselines_business_location_id",
        "onboarding_baselines",
        ["business_location_id"],
    )
    op.create_index(
        "ix_onboarding_baselines_generated_at",
        "onboarding_baselines",
        ["generated_at"],
    )
    op.create_index(
        "ix_onboarding_baselines_scope_generated",
        "onboarding_baselines",
        ["tenant_id", "organization_id", "campaign_id", "generated_at"],
    )

    if op.get_bind().dialect.name == "postgresql":
        scope = (
            "current_setting('app.platform_access', true) = 'on' OR ("
            "tenant_id::text = current_setting('app.current_tenant_id', true) AND "
            "organization_id::text = current_setting('app.current_organization_id', true))"
        )
        op.execute(
            sa.text(
                "GRANT SELECT, INSERT ON TABLE public.onboarding_baselines TO lsos_app"
            )
        )
        op.execute(
            sa.text(
                "REVOKE UPDATE, DELETE ON TABLE public.onboarding_baselines FROM lsos_app"
            )
        )
        op.execute(
            sa.text(
                "ALTER TABLE public.onboarding_baselines ENABLE ROW LEVEL SECURITY"
            )
        )
        op.execute(
            sa.text(
                "CREATE POLICY onboarding_baselines_scope ON public.onboarding_baselines "
                f"FOR ALL TO lsos_app USING ({scope}) WITH CHECK ({scope})"
            )
        )
        op.execute(
            sa.text(
                """
                CREATE OR REPLACE FUNCTION public.prevent_onboarding_baseline_mutation()
                RETURNS trigger
                LANGUAGE plpgsql
                AS $$
                BEGIN
                    IF current_setting('app.platform_maintenance', true) IS DISTINCT FROM 'on'
                    THEN
                        RAISE EXCEPTION 'onboarding baselines are append-only and immutable';
                    END IF;
                    IF TG_OP = 'DELETE' THEN
                        RETURN OLD;
                    END IF;
                    RETURN NEW;
                END;
                $$
                """
            )
        )
        op.execute(
            sa.text(
                """
                CREATE TRIGGER trg_onboarding_baselines_immutable
                BEFORE UPDATE OR DELETE ON public.onboarding_baselines
                FOR EACH ROW
                EXECUTE FUNCTION public.prevent_onboarding_baseline_mutation()
                """
            )
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            sa.text(
                "DROP TRIGGER IF EXISTS trg_onboarding_baselines_immutable "
                "ON public.onboarding_baselines"
            )
        )
        op.execute(
            sa.text(
                "DROP FUNCTION IF EXISTS public.prevent_onboarding_baseline_mutation()"
            )
        )
        op.execute(
            sa.text(
                "DROP POLICY IF EXISTS onboarding_baselines_scope "
                "ON public.onboarding_baselines"
            )
        )
    op.drop_index(
        "ix_onboarding_baselines_scope_generated",
        table_name="onboarding_baselines",
    )
    op.drop_index(
        "ix_onboarding_baselines_generated_at", table_name="onboarding_baselines"
    )
    op.drop_index(
        "ix_onboarding_baselines_business_location_id",
        table_name="onboarding_baselines",
    )
    op.drop_index(
        "ix_onboarding_baselines_campaign_id", table_name="onboarding_baselines"
    )
    op.drop_index(
        "ix_onboarding_baselines_organization_id",
        table_name="onboarding_baselines",
    )
    op.drop_index(
        "ix_onboarding_baselines_tenant_id", table_name="onboarding_baselines"
    )
    op.drop_table("onboarding_baselines")

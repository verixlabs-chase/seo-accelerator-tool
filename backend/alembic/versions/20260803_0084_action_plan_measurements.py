"""add action plan baselines and outcome measurement readiness

Revision ID: 20260803_0084
Revises: 20260803_0083
Create Date: 2026-08-03 18:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260803_0084"
down_revision = "20260803_0083"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "action_plan_measurements",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("campaign_id", sa.String(length=36), nullable=False),
        sa.Column("business_location_id", sa.String(length=36), nullable=True),
        sa.Column("occurrence_id", sa.String(length=36), nullable=False),
        sa.Column("recommendation_id", sa.String(length=36), nullable=False),
        sa.Column("action_id", sa.String(length=160), nullable=False),
        sa.Column(
            "measurement_status",
            sa.String(length=32),
            nullable=False,
            server_default="insufficient_baseline",
        ),
        sa.Column(
            "outcome_status",
            sa.String(length=32),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("success_metric_ids", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("baseline_metrics", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("baseline_evidence", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("implementation_scope", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("completion_proof", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("outcome_metrics", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("outcome_evidence", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("observation_window_days", sa.Integer(), nullable=False),
        sa.Column("evidence_window_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("evidence_window_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("observation_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("baseline_captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("work_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("outcome_measured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("action_plan_hash", sa.String(length=64), nullable=False),
        sa.Column("lexicon_id", sa.String(length=120), nullable=False),
        sa.Column("lexicon_version", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "measurement_status in ('baseline_ready','insufficient_baseline','waiting_for_results','measured')",
            name="ck_action_plan_measurements_status",
        ),
        sa.CheckConstraint(
            "outcome_status in ('pending','helped','did_not_help','insufficient_data')",
            name="ck_action_plan_measurements_outcome_status",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["business_location_id"],
            ["business_locations.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["occurrence_id"],
            ["action_plan_occurrences.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["recommendation_id"],
            ["strategy_recommendations.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "occurrence_id",
            name="uq_action_plan_measurements_occurrence_id",
        ),
    )
    for column in (
        "tenant_id",
        "organization_id",
        "campaign_id",
        "business_location_id",
        "occurrence_id",
        "recommendation_id",
        "action_id",
        "measurement_status",
        "outcome_status",
        "observation_due_at",
    ):
        op.create_index(
            f"ix_action_plan_measurements_{column}",
            "action_plan_measurements",
            [column],
        )
    op.create_index(
        "ix_action_plan_measurements_campaign_status_due",
        "action_plan_measurements",
        ["campaign_id", "measurement_status", "observation_due_at"],
    )

    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            sa.text(
                """
                GRANT SELECT, INSERT, UPDATE, DELETE
                    ON TABLE public.action_plan_measurements TO lsos_app;

                ALTER TABLE public.action_plan_measurements ENABLE ROW LEVEL SECURITY;
                DROP POLICY IF EXISTS lsos_tenant_isolation ON public.action_plan_measurements;
                CREATE POLICY lsos_tenant_isolation ON public.action_plan_measurements
                    FOR ALL TO lsos_app
                    USING (
                        current_setting('app.platform_access', true) = 'on'
                        OR (
                            tenant_id::text = current_setting('app.current_tenant_id', true)
                            AND organization_id::text = current_setting('app.current_organization_id', true)
                        )
                    )
                    WITH CHECK (
                        current_setting('app.platform_access', true) = 'on'
                        OR (
                            tenant_id::text = current_setting('app.current_tenant_id', true)
                            AND organization_id::text = current_setting('app.current_organization_id', true)
                        )
                    );

                CREATE OR REPLACE FUNCTION public.prevent_action_plan_baseline_mutation()
                RETURNS trigger
                LANGUAGE plpgsql
                AS $$
                BEGIN
                    IF NEW.success_metric_ids IS DISTINCT FROM OLD.success_metric_ids
                       OR NEW.baseline_metrics IS DISTINCT FROM OLD.baseline_metrics
                       OR NEW.baseline_evidence IS DISTINCT FROM OLD.baseline_evidence
                       OR NEW.implementation_scope IS DISTINCT FROM OLD.implementation_scope
                       OR NEW.observation_window_days IS DISTINCT FROM OLD.observation_window_days
                       OR NEW.evidence_window_start IS DISTINCT FROM OLD.evidence_window_start
                       OR NEW.evidence_window_end IS DISTINCT FROM OLD.evidence_window_end
                       OR NEW.baseline_captured_at IS DISTINCT FROM OLD.baseline_captured_at
                       OR NEW.action_plan_hash IS DISTINCT FROM OLD.action_plan_hash
                       OR NEW.lexicon_id IS DISTINCT FROM OLD.lexicon_id
                       OR NEW.lexicon_version IS DISTINCT FROM OLD.lexicon_version
                    THEN
                        RAISE EXCEPTION 'action plan baseline fields are immutable';
                    END IF;
                    RETURN NEW;
                END;
                $$;

                DROP TRIGGER IF EXISTS trg_action_plan_baseline_immutable
                    ON public.action_plan_measurements;
                CREATE TRIGGER trg_action_plan_baseline_immutable
                    BEFORE UPDATE ON public.action_plan_measurements
                    FOR EACH ROW
                    EXECUTE FUNCTION public.prevent_action_plan_baseline_mutation();
                """
            )
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            sa.text(
                """
                DROP TRIGGER IF EXISTS trg_action_plan_baseline_immutable
                    ON public.action_plan_measurements;
                DROP FUNCTION IF EXISTS public.prevent_action_plan_baseline_mutation();
                DROP POLICY IF EXISTS lsos_tenant_isolation ON public.action_plan_measurements;
                ALTER TABLE public.action_plan_measurements DISABLE ROW LEVEL SECURITY;
                """
            )
        )
    op.drop_index(
        "ix_action_plan_measurements_campaign_status_due",
        table_name="action_plan_measurements",
    )
    for column in reversed(
        (
            "tenant_id",
            "organization_id",
            "campaign_id",
            "business_location_id",
            "occurrence_id",
            "recommendation_id",
            "action_id",
            "measurement_status",
            "outcome_status",
            "observation_due_at",
        )
    ):
        op.drop_index(
            f"ix_action_plan_measurements_{column}",
            table_name="action_plan_measurements",
        )
    op.drop_table("action_plan_measurements")

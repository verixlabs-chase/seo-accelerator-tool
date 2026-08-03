"""add reproducible action plan forecast artifacts

Revision ID: 20260803_0085
Revises: 20260803_0084
Create Date: 2026-08-03 21:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260803_0085"
down_revision = "20260803_0084"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "action_plan_forecasts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("campaign_id", sa.String(length=36), nullable=False),
        sa.Column("business_location_id", sa.String(length=36), nullable=True),
        sa.Column("occurrence_id", sa.String(length=36), nullable=False),
        sa.Column("measurement_id", sa.String(length=36), nullable=False),
        sa.Column("recommendation_id", sa.String(length=36), nullable=False),
        sa.Column("action_id", sa.String(length=160), nullable=False),
        sa.Column("forecast_status", sa.String(length=24), nullable=False),
        sa.Column("metric_forecasts", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("assumptions", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("unavailable_reasons", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("data_quality", sa.String(length=24), nullable=False),
        sa.Column("model_id", sa.String(length=120), nullable=False),
        sa.Column("model_version", sa.String(length=40), nullable=False),
        sa.Column("model_parameters", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("artifact_hash", sa.String(length=64), nullable=False),
        sa.Column("action_plan_hash", sa.String(length=64), nullable=False),
        sa.Column("lexicon_id", sa.String(length=120), nullable=False),
        sa.Column("lexicon_version", sa.String(length=80), nullable=False),
        sa.Column("observation_window_days", sa.Integer(), nullable=False),
        sa.Column("outcome_comparisons", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("compared_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "forecast_status in ('available','not_available')",
            name="ck_action_plan_forecasts_status",
        ),
        sa.CheckConstraint(
            "data_quality in ('strong','moderate','insufficient')",
            name="ck_action_plan_forecasts_data_quality",
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
            ["measurement_id"],
            ["action_plan_measurements.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["recommendation_id"],
            ["strategy_recommendations.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("occurrence_id", name="uq_action_plan_forecasts_occurrence_id"),
    )
    for column in (
        "tenant_id",
        "organization_id",
        "campaign_id",
        "business_location_id",
        "occurrence_id",
        "measurement_id",
        "recommendation_id",
        "action_id",
        "forecast_status",
        "generated_at",
    ):
        op.create_index(
            f"ix_action_plan_forecasts_{column}",
            "action_plan_forecasts",
            [column],
        )
    op.create_index(
        "ix_action_plan_forecasts_campaign_status_generated",
        "action_plan_forecasts",
        ["campaign_id", "forecast_status", "generated_at"],
    )

    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            sa.text(
                """
                GRANT SELECT, INSERT, UPDATE, DELETE
                    ON TABLE public.action_plan_forecasts TO lsos_app;

                ALTER TABLE public.action_plan_forecasts ENABLE ROW LEVEL SECURITY;
                DROP POLICY IF EXISTS lsos_tenant_isolation ON public.action_plan_forecasts;
                CREATE POLICY lsos_tenant_isolation ON public.action_plan_forecasts
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

                CREATE OR REPLACE FUNCTION public.prevent_action_plan_forecast_mutation()
                RETURNS trigger
                LANGUAGE plpgsql
                AS $$
                BEGIN
                    IF NEW.measurement_id IS DISTINCT FROM OLD.measurement_id
                       OR NEW.action_id IS DISTINCT FROM OLD.action_id
                       OR NEW.forecast_status IS DISTINCT FROM OLD.forecast_status
                       OR NEW.metric_forecasts IS DISTINCT FROM OLD.metric_forecasts
                       OR NEW.assumptions IS DISTINCT FROM OLD.assumptions
                       OR NEW.unavailable_reasons IS DISTINCT FROM OLD.unavailable_reasons
                       OR NEW.data_quality IS DISTINCT FROM OLD.data_quality
                       OR NEW.model_id IS DISTINCT FROM OLD.model_id
                       OR NEW.model_version IS DISTINCT FROM OLD.model_version
                       OR NEW.model_parameters IS DISTINCT FROM OLD.model_parameters
                       OR NEW.input_hash IS DISTINCT FROM OLD.input_hash
                       OR NEW.artifact_hash IS DISTINCT FROM OLD.artifact_hash
                       OR NEW.action_plan_hash IS DISTINCT FROM OLD.action_plan_hash
                       OR NEW.lexicon_id IS DISTINCT FROM OLD.lexicon_id
                       OR NEW.lexicon_version IS DISTINCT FROM OLD.lexicon_version
                       OR NEW.observation_window_days IS DISTINCT FROM OLD.observation_window_days
                       OR NEW.generated_at IS DISTINCT FROM OLD.generated_at
                    THEN
                        RAISE EXCEPTION 'action plan forecast fields are immutable';
                    END IF;
                    RETURN NEW;
                END;
                $$;

                DROP TRIGGER IF EXISTS trg_action_plan_forecast_immutable
                    ON public.action_plan_forecasts;
                CREATE TRIGGER trg_action_plan_forecast_immutable
                    BEFORE UPDATE ON public.action_plan_forecasts
                    FOR EACH ROW
                    EXECUTE FUNCTION public.prevent_action_plan_forecast_mutation();
                """
            )
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            sa.text(
                """
                DROP TRIGGER IF EXISTS trg_action_plan_forecast_immutable
                    ON public.action_plan_forecasts;
                DROP FUNCTION IF EXISTS public.prevent_action_plan_forecast_mutation();
                DROP POLICY IF EXISTS lsos_tenant_isolation ON public.action_plan_forecasts;
                ALTER TABLE public.action_plan_forecasts DISABLE ROW LEVEL SECURITY;
                """
            )
        )
    op.drop_index(
        "ix_action_plan_forecasts_campaign_status_generated",
        table_name="action_plan_forecasts",
    )
    for column in reversed(
        (
            "tenant_id",
            "organization_id",
            "campaign_id",
            "business_location_id",
            "occurrence_id",
            "measurement_id",
            "recommendation_id",
            "action_id",
            "forecast_status",
            "generated_at",
        )
    ):
        op.drop_index(
            f"ix_action_plan_forecasts_{column}",
            table_name="action_plan_forecasts",
        )
    op.drop_table("action_plan_forecasts")

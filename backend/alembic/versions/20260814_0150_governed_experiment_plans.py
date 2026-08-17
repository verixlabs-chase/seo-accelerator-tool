"""add governed experiment plans

Revision ID: 20260814_0150
Revises: 20260814_0149
Create Date: 2026-08-14 14:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260814_0150"
down_revision = "20260814_0149"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "governed_experiment_plans",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("campaign_id", sa.String(36), nullable=False),
        sa.Column("business_location_id", sa.String(36), nullable=True),
        sa.Column("action_id", sa.String(160), nullable=False),
        sa.Column("metric_id", sa.String(160), nullable=False),
        sa.Column("measurement_contract_version", sa.String(80), nullable=False),
        sa.Column("hypothesis", sa.Text(), nullable=False),
        sa.Column("design_type", sa.String(40), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("minimum_sample_size", sa.Integer(), nullable=False),
        sa.Column("observation_window_days", sa.Integer(), nullable=False),
        sa.Column("guardrail_metric_ids", sa.JSON(), nullable=False),
        sa.Column("eligibility_snapshot", sa.JSON(), nullable=False),
        sa.Column("stop_rules", sa.JSON(), nullable=False),
        sa.Column("rollback_steps", sa.JSON(), nullable=False),
        sa.Column("design_version", sa.String(40), nullable=False),
        sa.Column("artifact_hash", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(64), nullable=False),
        sa.Column("created_by_user_id", sa.String(36), nullable=False),
        sa.Column("reviewed_by_user_id", sa.String(36), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "design_type in ('content_split','staggered_rollout','holdout_comparison')",
            name="ck_governed_experiment_plans_design_type",
        ),
        sa.CheckConstraint(
            "status in ('draft','approved','rejected','cancelled')",
            name="ck_governed_experiment_plans_status",
        ),
        sa.CheckConstraint(
            "minimum_sample_size >= 5 AND minimum_sample_size <= 1000",
            name="ck_governed_experiment_plans_sample_size",
        ),
        sa.CheckConstraint(
            "observation_window_days >= 7 AND observation_window_days <= 180",
            name="ck_governed_experiment_plans_observation_window",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["business_location_id"],
            ["business_locations.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "idempotency_key",
            name="uq_governed_experiment_plans_tenant_idempotency",
        ),
    )
    for column_name in (
        "tenant_id",
        "organization_id",
        "campaign_id",
        "business_location_id",
        "action_id",
        "metric_id",
        "status",
        "artifact_hash",
        "reviewed_at",
    ):
        op.create_index(
            f"ix_governed_experiment_plans_{column_name}",
            "governed_experiment_plans",
            [column_name],
        )
    op.create_index(
        "ix_governed_experiment_plans_campaign_status_created",
        "governed_experiment_plans",
        ["campaign_id", "status", "created_at"],
    )

    if op.get_bind().dialect.name == "postgresql":
        expression = (
            "current_setting('app.platform_access', true) = 'on' OR ("
            "tenant_id::text = current_setting('app.current_tenant_id', true) AND "
            "organization_id::text = current_setting('app.current_organization_id', true))"
        )
        op.execute(
            sa.text(
                "GRANT SELECT, INSERT, UPDATE, DELETE "
                "ON TABLE public.governed_experiment_plans TO lsos_app"
            )
        )
        op.execute(
            sa.text(
                "ALTER TABLE public.governed_experiment_plans ENABLE ROW LEVEL SECURITY"
            )
        )
        op.execute(
            sa.text(
                "CREATE POLICY lsos_tenant_isolation "
                "ON public.governed_experiment_plans FOR ALL TO lsos_app "
                f"USING ({expression}) WITH CHECK ({expression})"
            )
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            sa.text(
                "DROP POLICY IF EXISTS lsos_tenant_isolation "
                "ON public.governed_experiment_plans"
            )
        )
        op.execute(
            sa.text(
                "ALTER TABLE public.governed_experiment_plans DISABLE ROW LEVEL SECURITY"
            )
        )
    op.drop_table("governed_experiment_plans")

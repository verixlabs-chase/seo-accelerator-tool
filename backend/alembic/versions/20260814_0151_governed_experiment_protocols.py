"""add governed experiment monitoring protocols

Revision ID: 20260814_0151
Revises: 20260814_0150
Create Date: 2026-08-14 16:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260814_0151"
down_revision = "20260814_0150"
branch_labels = None
depends_on = None


def _tenant_policy(table_name: str) -> None:
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
        "governed_experiment_protocols",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("campaign_id", sa.String(36), nullable=False),
        sa.Column("business_location_id", sa.String(36), nullable=True),
        sa.Column("plan_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("protocol_version", sa.String(40), nullable=False),
        sa.Column("plan_artifact_hash", sa.String(64), nullable=False),
        sa.Column("protocol_hash", sa.String(64), nullable=False),
        sa.Column("baseline_snapshot", sa.JSON(), nullable=False),
        sa.Column("protected_baselines", sa.JSON(), nullable=False),
        sa.Column("allowance_baseline", sa.JSON(), nullable=False),
        sa.Column("stop_rules", sa.JSON(), nullable=False),
        sa.Column("rollback_steps", sa.JSON(), nullable=False),
        sa.Column("authorization_acknowledgements", sa.JSON(), nullable=False),
        sa.Column("change_evidence", sa.JSON(), nullable=False),
        sa.Column("latest_check_summary", sa.JSON(), nullable=False),
        sa.Column("stop_reason_code", sa.String(80), nullable=True),
        sa.Column("stop_note", sa.Text(), nullable=True),
        sa.Column("rollback_evidence", sa.JSON(), nullable=False),
        sa.Column("created_by_user_id", sa.String(36), nullable=False),
        sa.Column("authorized_by_user_id", sa.String(36), nullable=True),
        sa.Column("started_by_user_id", sa.String(36), nullable=True),
        sa.Column("stopped_by_user_id", sa.String(36), nullable=True),
        sa.Column("rollback_verified_by_user_id", sa.String(36), nullable=True),
        sa.Column("authorized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("monitoring_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("observation_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rollback_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status in ('prepared','authorized','monitoring','stop_required','rollback_pending','rollback_verified','completed','cancelled')",
            name="ck_governed_experiment_protocols_status",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["business_location_id"], ["business_locations.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"], ["governed_experiment_plans.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["authorized_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["started_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["stopped_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["rollback_verified_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "plan_id", name="uq_governed_experiment_protocols_tenant_plan"
        ),
    )
    for column_name in (
        "tenant_id",
        "organization_id",
        "campaign_id",
        "business_location_id",
        "plan_id",
        "status",
        "plan_artifact_hash",
        "protocol_hash",
    ):
        op.create_index(
            f"ix_governed_experiment_protocols_{column_name}",
            "governed_experiment_protocols",
            [column_name],
        )
    op.create_index(
        "ix_governed_experiment_protocols_campaign_status_created",
        "governed_experiment_protocols",
        ["campaign_id", "status", "created_at"],
    )

    op.create_table(
        "governed_experiment_guardrail_checks",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("protocol_id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("campaign_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("primary_metric", sa.JSON(), nullable=False),
        sa.Column("protected_metrics", sa.JSON(), nullable=False),
        sa.Column("allowance_snapshot", sa.JSON(), nullable=False),
        sa.Column("triggered_rules", sa.JSON(), nullable=False),
        sa.Column("artifact_hash", sa.String(64), nullable=False),
        sa.Column("checked_by_user_id", sa.String(36), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status in ('passed','waiting_for_fresh_data','stop_required','completed')",
            name="ck_governed_experiment_guardrail_checks_status",
        ),
        sa.ForeignKeyConstraint(
            ["protocol_id"], ["governed_experiment_protocols.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["checked_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    for column_name in (
        "protocol_id",
        "tenant_id",
        "organization_id",
        "campaign_id",
        "status",
        "artifact_hash",
        "checked_at",
    ):
        op.create_index(
            f"ix_governed_experiment_guardrail_checks_{column_name}",
            "governed_experiment_guardrail_checks",
            [column_name],
        )
    op.create_index(
        "ix_governed_experiment_checks_protocol_checked",
        "governed_experiment_guardrail_checks",
        ["protocol_id", "checked_at"],
    )

    _tenant_policy("governed_experiment_protocols")
    _tenant_policy("governed_experiment_guardrail_checks")


def downgrade() -> None:
    for table_name in (
        "governed_experiment_guardrail_checks",
        "governed_experiment_protocols",
    ):
        if op.get_bind().dialect.name == "postgresql":
            op.execute(
                sa.text(
                    f"DROP POLICY IF EXISTS lsos_tenant_isolation ON public.{table_name}"
                )
            )
            op.execute(
                sa.text(f"ALTER TABLE public.{table_name} DISABLE ROW LEVEL SECURITY")
            )
    op.drop_table("governed_experiment_guardrail_checks")
    op.drop_table("governed_experiment_protocols")

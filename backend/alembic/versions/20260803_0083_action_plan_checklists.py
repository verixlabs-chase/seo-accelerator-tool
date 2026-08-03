"""add persistent action plan checklists and routine occurrences

Revision ID: 20260803_0083
Revises: 20260730_0082
Create Date: 2026-08-03 16:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260803_0083"
down_revision = "20260730_0082"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "action_plan_occurrences",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("campaign_id", sa.String(length=36), nullable=False),
        sa.Column("business_location_id", sa.String(length=36), nullable=True),
        sa.Column("recommendation_id", sa.String(length=36), nullable=False),
        sa.Column("action_id", sa.String(length=160), nullable=False),
        sa.Column("cadence", sa.String(length=16), nullable=False),
        sa.Column("period_key", sa.String(length=32), nullable=False),
        sa.Column("timezone", sa.String(length=80), nullable=False, server_default="UTC"),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="ready"),
        sa.Column("lexicon_id", sa.String(length=120), nullable=False),
        sa.Column("lexicon_version", sa.String(length=80), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "cadence in ('daily','weekly','monthly','later')",
            name="ck_action_plan_occurrences_cadence",
        ),
        sa.CheckConstraint(
            "status in ('ready','in_progress','blocked','waiting_for_results','completed','dismissed','snoozed')",
            name="ck_action_plan_occurrences_status",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["business_location_id"], ["business_locations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["recommendation_id"], ["strategy_recommendations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "idempotency_key",
            name="uq_action_plan_occurrences_tenant_idempotency",
        ),
    )
    for column in (
        "tenant_id",
        "organization_id",
        "campaign_id",
        "business_location_id",
        "recommendation_id",
        "action_id",
        "status",
        "created_at",
    ):
        op.create_index(
            f"ix_action_plan_occurrences_{column}",
            "action_plan_occurrences",
            [column],
        )
    op.create_index(
        "ix_action_plan_occurrences_campaign_cadence_due",
        "action_plan_occurrences",
        ["campaign_id", "cadence", "due_at"],
    )
    op.create_index(
        "ix_action_plan_occurrences_recommendation_status",
        "action_plan_occurrences",
        ["recommendation_id", "status", "created_at"],
    )

    op.create_table(
        "action_plan_steps",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("occurrence_id", sa.String(length=36), nullable=False),
        sa.Column("step_key", sa.String(length=80), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("instruction", sa.Text(), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="not_started"),
        sa.Column("blocker_reason", sa.Text(), nullable=True),
        sa.Column("evidence", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("completed_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status in ('not_started','in_progress','done','skipped','blocked')",
            name="ck_action_plan_steps_status",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["occurrence_id"], ["action_plan_occurrences.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["completed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "occurrence_id",
            "step_key",
            name="uq_action_plan_steps_occurrence_key",
        ),
    )
    for column in (
        "tenant_id",
        "organization_id",
        "occurrence_id",
        "status",
    ):
        op.create_index(
            f"ix_action_plan_steps_{column}",
            "action_plan_steps",
            [column],
        )
    op.create_index(
        "ix_action_plan_steps_occurrence_position",
        "action_plan_steps",
        ["occurrence_id", "position"],
    )

    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            sa.text(
                """
                GRANT SELECT, INSERT, UPDATE, DELETE
                    ON TABLE public.action_plan_occurrences TO lsos_app;
                GRANT SELECT, INSERT, UPDATE, DELETE
                    ON TABLE public.action_plan_steps TO lsos_app;

                ALTER TABLE public.action_plan_occurrences ENABLE ROW LEVEL SECURITY;
                DROP POLICY IF EXISTS lsos_tenant_isolation ON public.action_plan_occurrences;
                CREATE POLICY lsos_tenant_isolation ON public.action_plan_occurrences
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

                ALTER TABLE public.action_plan_steps ENABLE ROW LEVEL SECURITY;
                DROP POLICY IF EXISTS lsos_tenant_isolation ON public.action_plan_steps;
                CREATE POLICY lsos_tenant_isolation ON public.action_plan_steps
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
                """
            )
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            sa.text(
                """
                DROP POLICY IF EXISTS lsos_tenant_isolation ON public.action_plan_steps;
                ALTER TABLE public.action_plan_steps DISABLE ROW LEVEL SECURITY;
                DROP POLICY IF EXISTS lsos_tenant_isolation ON public.action_plan_occurrences;
                ALTER TABLE public.action_plan_occurrences DISABLE ROW LEVEL SECURITY;
                """
            )
        )
    op.drop_index("ix_action_plan_steps_occurrence_position", table_name="action_plan_steps")
    for column in ("status", "occurrence_id", "organization_id", "tenant_id"):
        op.drop_index(f"ix_action_plan_steps_{column}", table_name="action_plan_steps")
    op.drop_table("action_plan_steps")

    op.drop_index(
        "ix_action_plan_occurrences_recommendation_status",
        table_name="action_plan_occurrences",
    )
    op.drop_index(
        "ix_action_plan_occurrences_campaign_cadence_due",
        table_name="action_plan_occurrences",
    )
    for column in (
        "created_at",
        "status",
        "action_id",
        "recommendation_id",
        "business_location_id",
        "campaign_id",
        "organization_id",
        "tenant_id",
    ):
        op.drop_index(
            f"ix_action_plan_occurrences_{column}",
            table_name="action_plan_occurrences",
        )
    op.drop_table("action_plan_occurrences")

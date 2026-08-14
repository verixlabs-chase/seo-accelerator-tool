"""add human outcome learning reviews

Revision ID: 20260814_0149
Revises: 20260813_0148
Create Date: 2026-08-14 12:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260814_0149"
down_revision = "20260813_0148"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "outcome_learning_reviews",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("campaign_id", sa.String(36), nullable=False),
        sa.Column("business_location_id", sa.String(36), nullable=True),
        sa.Column("measurement_id", sa.String(36), nullable=False),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("confounder_codes", sa.JSON(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("reviewed_by_user_id", sa.String(36), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "decision in ('pending','included','excluded')",
            name="ck_outcome_learning_reviews_decision",
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
            ["measurement_id"],
            ["action_plan_measurements.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "measurement_id",
            name="uq_outcome_learning_reviews_measurement_id",
        ),
    )
    for column_name in (
        "tenant_id",
        "organization_id",
        "campaign_id",
        "business_location_id",
        "measurement_id",
        "decision",
        "reviewed_at",
    ):
        op.create_index(
            f"ix_outcome_learning_reviews_{column_name}",
            "outcome_learning_reviews",
            [column_name],
        )
    op.create_index(
        "ix_outcome_learning_reviews_campaign_decision_reviewed",
        "outcome_learning_reviews",
        ["campaign_id", "decision", "reviewed_at"],
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
                "ON TABLE public.outcome_learning_reviews TO lsos_app"
            )
        )
        op.execute(
            sa.text(
                "ALTER TABLE public.outcome_learning_reviews ENABLE ROW LEVEL SECURITY"
            )
        )
        op.execute(
            sa.text(
                "CREATE POLICY lsos_tenant_isolation "
                "ON public.outcome_learning_reviews FOR ALL TO lsos_app "
                f"USING ({expression}) WITH CHECK ({expression})"
            )
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            sa.text(
                "DROP POLICY IF EXISTS lsos_tenant_isolation "
                "ON public.outcome_learning_reviews"
            )
        )
        op.execute(
            sa.text(
                "ALTER TABLE public.outcome_learning_reviews DISABLE ROW LEVEL SECURITY"
            )
        )
    op.drop_table("outcome_learning_reviews")

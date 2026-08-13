"""add bounded WordPress automation policies

Revision ID: 20260813_0136
Revises: 20260813_0135
Create Date: 2026-08-13 10:20:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260813_0136"
down_revision = "20260813_0135"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "wordpress_automation_policies",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("campaign_id", sa.String(36), nullable=False),
        sa.Column("automation_enabled", sa.Boolean(), nullable=False),
        sa.Column("emergency_stop", sa.Boolean(), nullable=False),
        sa.Column("allowed_action_types", sa.JSON(), nullable=False),
        sa.Column("allowed_url_prefixes", sa.JSON(), nullable=False),
        sa.Column("schedule_timezone", sa.String(64), nullable=False),
        sa.Column("schedule_days", sa.JSON(), nullable=False),
        sa.Column("window_start_local", sa.String(5), nullable=False),
        sa.Column("window_end_local", sa.String(5), nullable=False),
        sa.Column("blackout_windows", sa.JSON(), nullable=False),
        sa.Column("monthly_action_limit", sa.Integer(), nullable=False),
        sa.Column("risk_tier_ceiling", sa.Integer(), nullable=False),
        sa.Column("requires_manual_approval", sa.Boolean(), nullable=False),
        sa.Column("acknowledged_by", sa.String(120), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "monthly_action_limit >= 0 and monthly_action_limit <= 500",
            name="ck_wordpress_automation_policies_monthly_limit",
        ),
        sa.CheckConstraint(
            "risk_tier_ceiling >= 1 and risk_tier_ceiling <= 3",
            name="ck_wordpress_automation_policies_risk_ceiling",
        ),
        sa.CheckConstraint(
            "version >= 1",
            name="ck_wordpress_automation_policies_version",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "campaign_id",
            name="uq_wordpress_automation_policies_campaign",
        ),
    )
    for column in ("tenant_id", "organization_id", "campaign_id"):
        op.create_index(
            f"ix_wordpress_automation_policies_{column}",
            "wordpress_automation_policies",
            [column],
        )
    op.create_index(
        "ix_wordpress_automation_policies_org_enabled",
        "wordpress_automation_policies",
        ["organization_id", "automation_enabled"],
    )

    if op.get_bind().dialect.name == "postgresql":
        expression = (
            "current_setting('app.platform_access', true) = 'on' OR ("
            "tenant_id::text = current_setting('app.current_tenant_id', true) AND "
            "organization_id::text = current_setting('app.current_organization_id', true))"
        )
        op.execute(
            sa.text(
                "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE "
                "public.wordpress_automation_policies TO lsos_app"
            )
        )
        op.execute(
            sa.text(
                "ALTER TABLE public.wordpress_automation_policies ENABLE ROW LEVEL SECURITY"
            )
        )
        op.execute(
            sa.text(
                "CREATE POLICY lsos_tenant_isolation ON "
                "public.wordpress_automation_policies FOR ALL TO lsos_app "
                f"USING ({expression}) WITH CHECK ({expression})"
            )
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            sa.text(
                "DROP POLICY IF EXISTS lsos_tenant_isolation ON "
                "public.wordpress_automation_policies"
            )
        )
        op.execute(
            sa.text(
                "ALTER TABLE public.wordpress_automation_policies DISABLE ROW LEVEL SECURITY"
            )
        )
    op.drop_table("wordpress_automation_policies")

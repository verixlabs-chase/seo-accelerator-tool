"""add portfolio delegation and pause recovery

Revision ID: 20260811_0114
Revises: 20260811_0113
Create Date: 2026-08-11 11:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260811_0114"
down_revision = "20260811_0113"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "portfolio_location_access_grants",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("location_group_id", sa.String(36), nullable=False),
        sa.Column("access_role", sa.String(24), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="active"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by_user_id", sa.String(36), nullable=True),
        sa.Column("revoked_by_user_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["location_group_id", "organization_id"],
            ["portfolio_location_groups.id", "portfolio_location_groups.organization_id"],
            ondelete="CASCADE",
            name="fk_portfolio_access_grants_group_org",
        ),
        sa.ForeignKeyConstraint(
            ["user_id", "organization_id"],
            ["organization_memberships.user_id", "organization_memberships.organization_id"],
            ondelete="CASCADE",
            name="fk_portfolio_access_grants_membership",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["revoked_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint(
            "organization_id",
            "user_id",
            "location_group_id",
            name="uq_portfolio_access_grants_org_user_group",
        ),
        sa.CheckConstraint(
            "access_role in ('viewer','operator','approver')",
            name="ck_portfolio_access_grants_role",
        ),
        sa.CheckConstraint(
            "status in ('active','revoked')",
            name="ck_portfolio_access_grants_status",
        ),
        sa.CheckConstraint("version >= 1", name="ck_portfolio_access_grants_version"),
    )
    for column in (
        "tenant_id",
        "organization_id",
        "user_id",
        "location_group_id",
        "created_by_user_id",
        "revoked_by_user_id",
    ):
        op.create_index(
            f"ix_portfolio_location_access_grants_{column}",
            "portfolio_location_access_grants",
            [column],
        )
    op.create_index(
        "ix_portfolio_access_grants_org_status",
        "portfolio_location_access_grants",
        ["organization_id", "status"],
    )
    op.create_index(
        "ix_portfolio_access_grants_user_status",
        "portfolio_location_access_grants",
        ["user_id", "status"],
    )

    with op.batch_alter_table("portfolio_fleet_runs") as batch_op:
        batch_op.drop_constraint("ck_portfolio_fleet_runs_status", type_="check")
        batch_op.create_check_constraint(
            "ck_portfolio_fleet_runs_status",
            "status in ('awaiting_approval','blocked','running','paused','succeeded','partial','failed','cancelled')",
        )

    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            sa.text(
                "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE "
                "public.portfolio_location_access_grants TO lsos_app"
            )
        )
        op.execute(
            sa.text(
                "ALTER TABLE public.portfolio_location_access_grants "
                "ENABLE ROW LEVEL SECURITY"
            )
        )
        op.execute(
            sa.text(
                "CREATE POLICY lsos_tenant_isolation ON "
                "public.portfolio_location_access_grants FOR ALL TO lsos_app "
                "USING (current_setting('app.platform_access', true) = 'on' OR "
                "(tenant_id::text = current_setting('app.current_tenant_id', true) AND "
                "organization_id::text = current_setting('app.current_organization_id', true))) "
                "WITH CHECK (current_setting('app.platform_access', true) = 'on' OR "
                "(tenant_id::text = current_setting('app.current_tenant_id', true) AND "
                "organization_id::text = current_setting('app.current_organization_id', true)))"
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("portfolio_fleet_runs") as batch_op:
        batch_op.drop_constraint("ck_portfolio_fleet_runs_status", type_="check")
        batch_op.create_check_constraint(
            "ck_portfolio_fleet_runs_status",
            "status in ('awaiting_approval','blocked','running','succeeded','partial','failed','cancelled')",
        )
    op.drop_table("portfolio_location_access_grants")

"""add governed portfolio targeting

Revision ID: 20260810_0112
Revises: 20260810_0111
Create Date: 2026-08-10 23:45:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260810_0112"
down_revision = "20260810_0111"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "portfolio_location_groups",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="active"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by_user_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint(
            "organization_id", "name", name="uq_portfolio_location_groups_org_name"
        ),
        sa.UniqueConstraint(
            "id", "organization_id", name="uq_portfolio_location_groups_id_org"
        ),
        sa.CheckConstraint(
            "status in ('active','archived')",
            name="ck_portfolio_location_groups_status",
        ),
        sa.CheckConstraint(
            "version >= 1", name="ck_portfolio_location_groups_version"
        ),
    )
    op.create_table(
        "portfolio_location_group_members",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("location_group_id", sa.String(36), nullable=False),
        sa.Column("business_location_id", sa.String(36), nullable=False),
        sa.Column("added_by_user_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["location_group_id", "organization_id"],
            ["portfolio_location_groups.id", "portfolio_location_groups.organization_id"],
            ondelete="CASCADE",
            name="fk_portfolio_location_group_members_group_org",
        ),
        sa.ForeignKeyConstraint(
            ["business_location_id", "organization_id"],
            ["business_locations.id", "business_locations.organization_id"],
            ondelete="CASCADE",
            name="fk_portfolio_location_group_members_location_org",
        ),
        sa.ForeignKeyConstraint(
            ["added_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint(
            "location_group_id",
            "business_location_id",
            name="uq_portfolio_location_group_members_group_location",
        ),
    )
    op.create_table(
        "portfolio_target_snapshots",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("location_group_id", sa.String(36), nullable=True),
        sa.Column("location_group_version", sa.Integer(), nullable=True),
        sa.Column("action_key", sa.String(80), nullable=False),
        sa.Column("request_key", sa.String(120), nullable=False),
        sa.Column("selection_mode", sa.String(32), nullable=False),
        sa.Column("selection_json", sa.JSON(), nullable=False),
        sa.Column("targets_json", sa.JSON(), nullable=False),
        sa.Column("exceptions_json", sa.JSON(), nullable=False),
        sa.Column("target_hash", sa.String(64), nullable=False),
        sa.Column("target_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("blocked_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by_user_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["location_group_id", "organization_id"],
            ["portfolio_location_groups.id", "portfolio_location_groups.organization_id"],
            name="fk_portfolio_target_snapshots_group_org",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint(
            "organization_id",
            "request_key",
            name="uq_portfolio_target_snapshots_org_request_key",
        ),
        sa.CheckConstraint(
            "selection_mode in ('group','all_active','explicit')",
            name="ck_portfolio_target_snapshots_selection_mode",
        ),
        sa.CheckConstraint(
            "target_count >= 0", name="ck_portfolio_target_snapshots_target_count"
        ),
        sa.CheckConstraint(
            "blocked_count >= 0", name="ck_portfolio_target_snapshots_blocked_count"
        ),
    )

    indexes = {
        "portfolio_location_groups": (
            "tenant_id",
            "organization_id",
            "created_by_user_id",
        ),
        "portfolio_location_group_members": (
            "tenant_id",
            "organization_id",
            "location_group_id",
            "business_location_id",
            "added_by_user_id",
        ),
        "portfolio_target_snapshots": (
            "tenant_id",
            "organization_id",
            "location_group_id",
            "target_hash",
            "created_by_user_id",
        ),
    }
    for table, columns in indexes.items():
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column])
    op.create_index(
        "ix_portfolio_location_groups_org_status",
        "portfolio_location_groups",
        ["organization_id", "status"],
    )
    op.create_index(
        "ix_portfolio_location_group_members_org_group",
        "portfolio_location_group_members",
        ["organization_id", "location_group_id"],
    )
    op.create_index(
        "ix_portfolio_target_snapshots_org_created",
        "portfolio_target_snapshots",
        ["organization_id", "created_at"],
    )
    op.create_index(
        "ix_portfolio_target_snapshots_group_created",
        "portfolio_target_snapshots",
        ["location_group_id", "created_at"],
    )

    if op.get_bind().dialect.name == "postgresql":
        for table in ("portfolio_location_groups", "portfolio_location_group_members"):
            op.execute(
                sa.text(
                    f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.{table} TO lsos_app"
                )
            )
            _create_full_access_policy(table)

        op.execute(
            sa.text(
                "GRANT SELECT, INSERT ON TABLE public.portfolio_target_snapshots TO lsos_app"
            )
        )
        op.execute(
            sa.text(
                "ALTER TABLE public.portfolio_target_snapshots ENABLE ROW LEVEL SECURITY"
            )
        )
        tenant_scope = (
            "current_setting('app.platform_access', true) = 'on' OR "
            "(tenant_id::text = current_setting('app.current_tenant_id', true) AND "
            "organization_id::text = current_setting('app.current_organization_id', true))"
        )
        op.execute(
            sa.text(
                "CREATE POLICY lsos_target_snapshot_read ON public.portfolio_target_snapshots "
                f"FOR SELECT TO lsos_app USING ({tenant_scope})"
            )
        )
        op.execute(
            sa.text(
                "CREATE POLICY lsos_target_snapshot_insert ON public.portfolio_target_snapshots "
                f"FOR INSERT TO lsos_app WITH CHECK ({tenant_scope})"
            )
        )


def _create_full_access_policy(table: str) -> None:
    op.execute(sa.text(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY"))
    op.execute(
        sa.text(
            f"CREATE POLICY lsos_tenant_isolation ON public.{table} FOR ALL TO lsos_app "
            "USING (current_setting('app.platform_access', true) = 'on' OR "
            "(tenant_id::text = current_setting('app.current_tenant_id', true) AND "
            "organization_id::text = current_setting('app.current_organization_id', true))) "
            "WITH CHECK (current_setting('app.platform_access', true) = 'on' OR "
            "(tenant_id::text = current_setting('app.current_tenant_id', true) AND "
            "organization_id::text = current_setting('app.current_organization_id', true)))"
        )
    )


def downgrade() -> None:
    op.drop_table("portfolio_target_snapshots")
    op.drop_table("portfolio_location_group_members")
    op.drop_table("portfolio_location_groups")

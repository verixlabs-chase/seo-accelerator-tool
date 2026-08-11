"""add approval-gated portfolio fleet runs

Revision ID: 20260811_0113
Revises: 20260810_0112
Create Date: 2026-08-11 09:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260811_0113"
down_revision = "20260810_0112"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "portfolio_fleet_runs",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("target_snapshot_id", sa.String(36), nullable=False),
        sa.Column("action_key", sa.String(80), nullable=False),
        sa.Column("request_key", sa.String(120), nullable=False),
        sa.Column("target_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="awaiting_approval"),
        sa.Column("preflight_json", sa.JSON(), nullable=False),
        sa.Column("target_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ready_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("blocked_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("queued_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("running_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("succeeded_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("estimated_credit_units", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("requested_by_user_id", sa.String(36), nullable=True),
        sa.Column("approved_by_user_id", sa.String(36), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["target_snapshot_id"],
            ["portfolio_target_snapshots.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["approved_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint(
            "organization_id",
            "request_key",
            name="uq_portfolio_fleet_runs_org_request_key",
        ),
        sa.CheckConstraint(
            "status in ('awaiting_approval','blocked','running','succeeded','partial','failed','cancelled')",
            name="ck_portfolio_fleet_runs_status",
        ),
        sa.CheckConstraint("version >= 1", name="ck_portfolio_fleet_runs_version"),
        sa.CheckConstraint(
            "estimated_credit_units >= 0",
            name="ck_portfolio_fleet_runs_estimated_credits",
        ),
        sa.CheckConstraint(
            "target_count >= 0 and ready_count >= 0 and blocked_count >= 0 and "
            "queued_count >= 0 and running_count >= 0 and succeeded_count >= 0 and "
            "failed_count >= 0",
            name="ck_portfolio_fleet_runs_nonnegative_counts",
        ),
    )
    op.create_table(
        "portfolio_fleet_run_items",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("portfolio_fleet_run_id", sa.String(36), nullable=False),
        sa.Column("business_location_id", sa.String(36), nullable=False),
        sa.Column("campaign_id", sa.String(36), nullable=True),
        sa.Column("portfolio_id", sa.String(36), nullable=True),
        sa.Column("fleet_job_id", sa.String(36), nullable=True),
        sa.Column("item_key", sa.String(160), nullable=False),
        sa.Column("location_name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="ready"),
        sa.Column("capability_json", sa.JSON(), nullable=False),
        sa.Column("estimated_credit_units", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_code", sa.String(80), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("retries", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["portfolio_fleet_run_id"],
            ["portfolio_fleet_runs.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["business_location_id"], ["business_locations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["portfolio_id"], ["portfolios.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["fleet_job_id"], ["fleet_jobs.id"], ondelete="SET NULL"),
        sa.UniqueConstraint(
            "portfolio_fleet_run_id",
            "business_location_id",
            name="uq_portfolio_fleet_run_items_run_location",
        ),
        sa.UniqueConstraint(
            "portfolio_fleet_run_id",
            "item_key",
            name="uq_portfolio_fleet_run_items_run_key",
        ),
        sa.CheckConstraint(
            "status in ('ready','blocked','queued','running','succeeded','failed')",
            name="ck_portfolio_fleet_run_items_status",
        ),
        sa.CheckConstraint("retries >= 0", name="ck_portfolio_fleet_run_items_retries"),
        sa.CheckConstraint(
            "estimated_credit_units >= 0",
            name="ck_portfolio_fleet_run_items_estimated_credits",
        ),
    )

    indexes = {
        "portfolio_fleet_runs": (
            "tenant_id",
            "organization_id",
            "target_snapshot_id",
            "target_hash",
            "status",
            "requested_by_user_id",
            "approved_by_user_id",
        ),
        "portfolio_fleet_run_items": (
            "tenant_id",
            "organization_id",
            "portfolio_fleet_run_id",
            "fleet_job_id",
        ),
    }
    for table, columns in indexes.items():
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column])
    op.create_index(
        "ix_portfolio_fleet_runs_org_created",
        "portfolio_fleet_runs",
        ["organization_id", "created_at"],
    )
    op.create_index(
        "ix_portfolio_fleet_runs_org_status",
        "portfolio_fleet_runs",
        ["organization_id", "status"],
    )
    op.create_index(
        "ix_portfolio_fleet_run_items_run_status",
        "portfolio_fleet_run_items",
        ["portfolio_fleet_run_id", "status"],
    )

    if op.get_bind().dialect.name == "postgresql":
        for table in ("portfolio_fleet_runs", "portfolio_fleet_run_items"):
            op.execute(
                sa.text(
                    f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.{table} TO lsos_app"
                )
            )
            _create_full_access_policy(table)


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
    op.drop_table("portfolio_fleet_run_items")
    op.drop_table("portfolio_fleet_runs")

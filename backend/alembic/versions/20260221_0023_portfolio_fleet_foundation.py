"""portfolio and fleet domain foundation

Revision ID: 20260221_0023
Revises: 20260220_0022
Create Date: 2026-02-21 12:20:00
"""

from __future__ import annotations

from alembic import context
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260221_0023"
down_revision = "20260220_0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    offline = context.is_offline_mode()
    inspector = None if offline else sa.inspect(bind)
    tables = set() if offline else set(inspector.get_table_names())

    json_type = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")

    if offline or "portfolios" not in tables:
        op.create_table(
            "portfolios",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column(
                "organization_id",
                sa.String(length=36),
                sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("name", sa.String(length=160), nullable=False),
            sa.Column("code", sa.String(length=64), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
            sa.Column("timezone", sa.String(length=80), nullable=False, server_default="UTC"),
            sa.Column("default_sla_tier", sa.String(length=20), nullable=False, server_default="standard"),
            sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("organization_id", "code", name="uq_portfolios_org_code"),
        )
    _create_index_if_missing(
        inspector=inspector,
        offline=offline,
        table_name="portfolios",
        index_name="ix_portfolios_organization_id",
        columns=["organization_id"],
    )
    _create_index_if_missing(
        inspector=inspector,
        offline=offline,
        table_name="portfolios",
        index_name="ix_portfolios_status",
        columns=["status"],
    )
    _create_index_if_missing(
        inspector=inspector,
        offline=offline,
        table_name="portfolios",
        index_name="ix_portfolios_org_status",
        columns=["organization_id", "status"],
    )

    if offline or "locations" not in tables:
        op.create_table(
            "locations",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column(
                "organization_id",
                sa.String(length=36),
                sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("portfolio_id", sa.String(length=36), sa.ForeignKey("portfolios.id", ondelete="SET NULL"), nullable=True),
            sa.Column(
                "sub_account_id",
                sa.String(length=36),
                sa.ForeignKey("sub_accounts.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("campaign_id", sa.String(length=36), sa.ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True),
            sa.Column("location_code", sa.String(length=64), nullable=False),
            sa.Column("name", sa.String(length=160), nullable=False),
            sa.Column("country_code", sa.String(length=2), nullable=False),
            sa.Column("region", sa.String(length=120), nullable=True),
            sa.Column("city", sa.String(length=120), nullable=True),
            sa.Column("lat", sa.Numeric(9, 6), nullable=True),
            sa.Column("lng", sa.Numeric(9, 6), nullable=True),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("organization_id", "location_code", name="uq_locations_org_location_code"),
        )
    _create_index_if_missing(inspector=inspector, offline=offline, table_name="locations", index_name="ix_locations_organization_id", columns=["organization_id"])
    _create_index_if_missing(inspector=inspector, offline=offline, table_name="locations", index_name="ix_locations_portfolio_id", columns=["portfolio_id"])
    _create_index_if_missing(inspector=inspector, offline=offline, table_name="locations", index_name="ix_locations_sub_account_id", columns=["sub_account_id"])
    _create_index_if_missing(inspector=inspector, offline=offline, table_name="locations", index_name="ix_locations_campaign_id", columns=["campaign_id"])
    _create_index_if_missing(inspector=inspector, offline=offline, table_name="locations", index_name="ix_locations_status", columns=["status"])
    _create_index_if_missing(
        inspector=inspector,
        offline=offline,
        table_name="locations",
        index_name="ix_locations_portfolio_status",
        columns=["portfolio_id", "status"],
    )
    _create_index_if_missing(
        inspector=inspector,
        offline=offline,
        table_name="locations",
        index_name="ix_locations_sub_account_status",
        columns=["sub_account_id", "status"],
    )

    if offline or "portfolio_policies" not in tables:
        op.create_table(
            "portfolio_policies",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column(
                "portfolio_id",
                sa.String(length=36),
                sa.ForeignKey("portfolios.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("policy_type", sa.String(length=40), nullable=False),
            sa.Column("policy_json", json_type, nullable=False, server_default=sa.text("'{}'")),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_by", sa.String(length=36), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("portfolio_id", "policy_type", name="uq_portfolio_policies_portfolio_type"),
        )
    _create_index_if_missing(
        inspector=inspector,
        offline=offline,
        table_name="portfolio_policies",
        index_name="ix_portfolio_policies_portfolio_id",
        columns=["portfolio_id"],
    )
    _create_index_if_missing(
        inspector=inspector,
        offline=offline,
        table_name="portfolio_policies",
        index_name="ix_portfolio_policies_portfolio_updated_at",
        columns=["portfolio_id", "updated_at"],
    )

    if offline or "fleet_jobs" not in tables:
        op.create_table(
            "fleet_jobs",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column(
                "organization_id",
                sa.String(length=36),
                sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "portfolio_id",
                sa.String(length=36),
                sa.ForeignKey("portfolios.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("job_type", sa.String(length=40), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("requested_by", sa.String(length=36), nullable=True),
            sa.Column("request_payload", json_type, nullable=False, server_default=sa.text("'{}'")),
            sa.Column("summary_json", json_type, nullable=False, server_default=sa.text("'{}'")),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        )
    _create_index_if_missing(inspector=inspector, offline=offline, table_name="fleet_jobs", index_name="ix_fleet_jobs_organization_id", columns=["organization_id"])
    _create_index_if_missing(inspector=inspector, offline=offline, table_name="fleet_jobs", index_name="ix_fleet_jobs_portfolio_id", columns=["portfolio_id"])
    _create_index_if_missing(
        inspector=inspector,
        offline=offline,
        table_name="fleet_jobs",
        index_name="ix_fleet_jobs_portfolio_created_at",
        columns=["portfolio_id", "created_at"],
    )
    _create_index_if_missing(
        inspector=inspector,
        offline=offline,
        table_name="fleet_jobs",
        index_name="ix_fleet_jobs_org_status_created_at",
        columns=["organization_id", "status", "created_at"],
    )

    if offline or "fleet_job_items" not in tables:
        op.create_table(
            "fleet_job_items",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column(
                "fleet_job_id",
                sa.String(length=36),
                sa.ForeignKey("fleet_jobs.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("item_key", sa.String(length=160), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
            sa.Column("error_code", sa.String(length=64), nullable=True),
            sa.Column("error_detail", sa.Text(), nullable=True),
            sa.Column("retries", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("fleet_job_id", "item_key", name="uq_fleet_job_items_job_item_key"),
        )
    _create_index_if_missing(inspector=inspector, offline=offline, table_name="fleet_job_items", index_name="ix_fleet_job_items_fleet_job_id", columns=["fleet_job_id"])
    _create_index_if_missing(
        inspector=inspector,
        offline=offline,
        table_name="fleet_job_items",
        index_name="ix_fleet_job_items_job_status",
        columns=["fleet_job_id", "status"],
    )

    _add_org_and_portfolio_columns(
        table_name="campaigns",
        org_fk_name="fk_campaigns_organization_id",
        portfolio_fk_name="fk_campaigns_portfolio_id",
        offline=offline,
    )
    if not offline:
        _ensure_legacy_organizations_for_table("campaigns")
        op.execute("UPDATE campaigns SET organization_id = tenant_id WHERE organization_id IS NULL")
    _create_index_if_missing(
        inspector=inspector,
        offline=offline,
        table_name="campaigns",
        index_name="ix_campaigns_org_portfolio_setup_state",
        columns=["organization_id", "portfolio_id", "setup_state"],
    )

    _add_org_and_portfolio_columns(
        table_name="report_schedules",
        org_fk_name="fk_report_schedules_organization_id",
        portfolio_fk_name="fk_report_schedules_portfolio_id",
        offline=offline,
    )
    if not offline:
        _ensure_legacy_organizations_for_table("report_schedules")
        op.execute("UPDATE report_schedules SET organization_id = tenant_id WHERE organization_id IS NULL")
    _create_index_if_missing(
        inspector=inspector,
        offline=offline,
        table_name="report_schedules",
        index_name="ix_report_schedules_org_portfolio_next_run_at",
        columns=["organization_id", "portfolio_id", "next_run_at"],
    )

    _add_org_and_portfolio_columns(
        table_name="provider_execution_metrics",
        org_fk_name="fk_provider_execution_metrics_organization_id",
        portfolio_fk_name="fk_provider_execution_metrics_portfolio_id",
        offline=offline,
    )
    if not offline:
        _ensure_legacy_organizations_for_table("provider_execution_metrics")
        op.execute("UPDATE provider_execution_metrics SET organization_id = tenant_id WHERE organization_id IS NULL")
    _create_index_if_missing(
        inspector=inspector,
        offline=offline,
        table_name="provider_execution_metrics",
        index_name="ix_provider_execution_metrics_org_portfolio_created_at",
        columns=["organization_id", "portfolio_id", "created_at"],
    )

    _add_org_and_portfolio_columns(
        table_name="task_executions",
        org_fk_name="fk_task_executions_organization_id",
        portfolio_fk_name="fk_task_executions_portfolio_id",
        offline=offline,
    )
    if not offline:
        _ensure_legacy_organizations_for_table("task_executions")
        op.execute("UPDATE task_executions SET organization_id = tenant_id WHERE organization_id IS NULL")
    _create_index_if_missing(
        inspector=inspector,
        offline=offline,
        table_name="task_executions",
        index_name="ix_task_executions_org_portfolio_created_at",
        columns=["organization_id", "portfolio_id", "created_at"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    offline = context.is_offline_mode()
    inspector = None if offline else sa.inspect(bind)

    _drop_org_and_portfolio_columns(
        inspector=inspector,
        offline=offline,
        table_name="task_executions",
        org_fk_name="fk_task_executions_organization_id",
        portfolio_fk_name="fk_task_executions_portfolio_id",
        org_index_name="ix_task_executions_organization_id",
        portfolio_index_name="ix_task_executions_portfolio_id",
        composite_index_name="ix_task_executions_org_portfolio_created_at",
    )
    _drop_org_and_portfolio_columns(
        inspector=inspector,
        offline=offline,
        table_name="provider_execution_metrics",
        org_fk_name="fk_provider_execution_metrics_organization_id",
        portfolio_fk_name="fk_provider_execution_metrics_portfolio_id",
        org_index_name="ix_provider_execution_metrics_organization_id",
        portfolio_index_name="ix_provider_execution_metrics_portfolio_id",
        composite_index_name="ix_provider_execution_metrics_org_portfolio_created_at",
    )
    _drop_org_and_portfolio_columns(
        inspector=inspector,
        offline=offline,
        table_name="report_schedules",
        org_fk_name="fk_report_schedules_organization_id",
        portfolio_fk_name="fk_report_schedules_portfolio_id",
        org_index_name="ix_report_schedules_organization_id",
        portfolio_index_name="ix_report_schedules_portfolio_id",
        composite_index_name="ix_report_schedules_org_portfolio_next_run_at",
    )
    _drop_org_and_portfolio_columns(
        inspector=inspector,
        offline=offline,
        table_name="campaigns",
        org_fk_name="fk_campaigns_organization_id",
        portfolio_fk_name="fk_campaigns_portfolio_id",
        org_index_name="ix_campaigns_organization_id",
        portfolio_index_name="ix_campaigns_portfolio_id",
        composite_index_name="ix_campaigns_org_portfolio_setup_state",
    )

    tables = set() if offline else set(inspector.get_table_names())
    if offline or "fleet_job_items" in tables:
        _drop_index_if_exists(inspector, offline, "fleet_job_items", "ix_fleet_job_items_job_status")
        _drop_index_if_exists(inspector, offline, "fleet_job_items", "ix_fleet_job_items_fleet_job_id")
        op.drop_table("fleet_job_items")

    if offline or "fleet_jobs" in tables:
        _drop_index_if_exists(inspector, offline, "fleet_jobs", "ix_fleet_jobs_org_status_created_at")
        _drop_index_if_exists(inspector, offline, "fleet_jobs", "ix_fleet_jobs_portfolio_created_at")
        _drop_index_if_exists(inspector, offline, "fleet_jobs", "ix_fleet_jobs_portfolio_id")
        _drop_index_if_exists(inspector, offline, "fleet_jobs", "ix_fleet_jobs_organization_id")
        op.drop_table("fleet_jobs")

    if offline or "portfolio_policies" in tables:
        _drop_index_if_exists(inspector, offline, "portfolio_policies", "ix_portfolio_policies_portfolio_updated_at")
        _drop_index_if_exists(inspector, offline, "portfolio_policies", "ix_portfolio_policies_portfolio_id")
        op.drop_table("portfolio_policies")

    if offline or "locations" in tables:
        _drop_index_if_exists(inspector, offline, "locations", "ix_locations_sub_account_status")
        _drop_index_if_exists(inspector, offline, "locations", "ix_locations_portfolio_status")
        _drop_index_if_exists(inspector, offline, "locations", "ix_locations_status")
        _drop_index_if_exists(inspector, offline, "locations", "ix_locations_campaign_id")
        _drop_index_if_exists(inspector, offline, "locations", "ix_locations_sub_account_id")
        _drop_index_if_exists(inspector, offline, "locations", "ix_locations_portfolio_id")
        _drop_index_if_exists(inspector, offline, "locations", "ix_locations_organization_id")
        op.drop_table("locations")

    if offline or "portfolios" in tables:
        _drop_index_if_exists(inspector, offline, "portfolios", "ix_portfolios_org_status")
        _drop_index_if_exists(inspector, offline, "portfolios", "ix_portfolios_status")
        _drop_index_if_exists(inspector, offline, "portfolios", "ix_portfolios_organization_id")
        op.drop_table("portfolios")


def _add_org_and_portfolio_columns(*, table_name: str, org_fk_name: str, portfolio_fk_name: str, offline: bool) -> None:
    bind = op.get_bind()
    inspector = None if offline else sa.inspect(bind)

    if offline:
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.add_column(sa.Column("organization_id", sa.String(length=36), nullable=True))
            batch_op.add_column(sa.Column("portfolio_id", sa.String(length=36), nullable=True))
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.create_foreign_key(org_fk_name, "organizations", ["organization_id"], ["id"], ondelete="SET NULL")
            batch_op.create_foreign_key(portfolio_fk_name, "portfolios", ["portfolio_id"], ["id"], ondelete="SET NULL")
        _create_index_if_missing(
            inspector=inspector,
            offline=offline,
            table_name=table_name,
            index_name=f"ix_{table_name}_organization_id",
            columns=["organization_id"],
        )
        _create_index_if_missing(
            inspector=inspector,
            offline=offline,
            table_name=table_name,
            index_name=f"ix_{table_name}_portfolio_id",
            columns=["portfolio_id"],
        )
        return

    columns = {column["name"] for column in inspector.get_columns(table_name)}
    if "organization_id" not in columns:
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.add_column(sa.Column("organization_id", sa.String(length=36), nullable=True))
    if "portfolio_id" not in columns:
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.add_column(sa.Column("portfolio_id", sa.String(length=36), nullable=True))

    inspector = sa.inspect(bind)
    foreign_keys = {fk["name"] for fk in inspector.get_foreign_keys(table_name)}
    if org_fk_name not in foreign_keys:
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.create_foreign_key(org_fk_name, "organizations", ["organization_id"], ["id"], ondelete="SET NULL")
    if portfolio_fk_name not in foreign_keys:
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.create_foreign_key(portfolio_fk_name, "portfolios", ["portfolio_id"], ["id"], ondelete="SET NULL")

    _create_index_if_missing(
        inspector=sa.inspect(bind),
        offline=offline,
        table_name=table_name,
        index_name=f"ix_{table_name}_organization_id",
        columns=["organization_id"],
    )
    _create_index_if_missing(
        inspector=sa.inspect(bind),
        offline=offline,
        table_name=table_name,
        index_name=f"ix_{table_name}_portfolio_id",
        columns=["portfolio_id"],
    )


def _drop_org_and_portfolio_columns(
    *,
    inspector: sa.Inspector | None,
    offline: bool,
    table_name: str,
    org_fk_name: str,
    portfolio_fk_name: str,
    org_index_name: str,
    portfolio_index_name: str,
    composite_index_name: str,
) -> None:
    if offline:
        _drop_index_if_exists(inspector, offline, table_name, composite_index_name)
        _drop_index_if_exists(inspector, offline, table_name, portfolio_index_name)
        _drop_index_if_exists(inspector, offline, table_name, org_index_name)
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.drop_constraint(portfolio_fk_name, type_="foreignkey")
            batch_op.drop_constraint(org_fk_name, type_="foreignkey")
            batch_op.drop_column("portfolio_id")
            batch_op.drop_column("organization_id")
        return

    columns = {column["name"] for column in inspector.get_columns(table_name)}
    if "organization_id" not in columns and "portfolio_id" not in columns:
        return

    _drop_index_if_exists(inspector, offline, table_name, composite_index_name)
    _drop_index_if_exists(sa.inspect(op.get_bind()), offline, table_name, portfolio_index_name)
    _drop_index_if_exists(sa.inspect(op.get_bind()), offline, table_name, org_index_name)

    foreign_keys = {fk["name"] for fk in sa.inspect(op.get_bind()).get_foreign_keys(table_name)}
    with op.batch_alter_table(table_name) as batch_op:
        if portfolio_fk_name in foreign_keys:
            batch_op.drop_constraint(portfolio_fk_name, type_="foreignkey")
        if org_fk_name in foreign_keys:
            batch_op.drop_constraint(org_fk_name, type_="foreignkey")
        if "portfolio_id" in columns:
            batch_op.drop_column("portfolio_id")
        if "organization_id" in columns:
            batch_op.drop_column("organization_id")


def _create_index_if_missing(*, inspector: sa.Inspector | None, offline: bool, table_name: str, index_name: str, columns: list[str]) -> None:
    if offline:
        op.create_index(index_name, table_name, columns)
        return

    indexes = {index["name"] for index in inspector.get_indexes(table_name)}
    if index_name not in indexes:
        op.create_index(index_name, table_name, columns)


def _drop_index_if_exists(inspector: sa.Inspector | None, offline: bool, table_name: str, index_name: str) -> None:
    if offline:
        op.drop_index(index_name, table_name=table_name)
        return

    indexes = {index["name"] for index in inspector.get_indexes(table_name)}
    if index_name in indexes:
        op.drop_index(index_name, table_name=table_name)


def _ensure_legacy_organizations_for_table(table_name: str) -> None:
    op.execute(
        sa.text(
            f"""
            INSERT INTO organizations (id, name, plan_type, billing_mode, status, created_at, updated_at)
            SELECT src.tenant_id, 'Legacy Org ' || src.tenant_id, 'standard', 'subscription', 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            FROM (
                SELECT DISTINCT tenant_id
                FROM {table_name}
                WHERE tenant_id IS NOT NULL
            ) AS src
            WHERE NOT EXISTS (
                SELECT 1 FROM organizations o WHERE o.id = src.tenant_id
            )
            """
        )
    )

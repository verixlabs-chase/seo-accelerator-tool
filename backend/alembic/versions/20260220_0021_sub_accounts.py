"""add organization sub-account structure

Revision ID: 20260220_0021
Revises: 20260220_0020
Create Date: 2026-02-20 01:15:00
"""

from __future__ import annotations

from alembic import context
from alembic import op
import sqlalchemy as sa


revision = "20260220_0021"
down_revision = "20260220_0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    offline = context.is_offline_mode()
    inspector = None if offline else sa.inspect(bind)
    tables = set() if offline else set(inspector.get_table_names())

    if offline or "sub_accounts" not in tables:
        op.create_table(
            "sub_accounts",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column(
                "organization_id",
                sa.String(length=36),
                sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("organization_id", "name", name="uq_sub_accounts_org_name"),
        )

    if offline:
        op.create_index("ix_sub_accounts_organization_id", "sub_accounts", ["organization_id"])
        op.create_index("ix_sub_accounts_org_status", "sub_accounts", ["organization_id", "status"])
    else:
        sub_indexes = {idx["name"] for idx in inspector.get_indexes("sub_accounts")}
        if "ix_sub_accounts_organization_id" not in sub_indexes:
            op.create_index("ix_sub_accounts_organization_id", "sub_accounts", ["organization_id"])
        if "ix_sub_accounts_org_status" not in sub_indexes:
            op.create_index("ix_sub_accounts_org_status", "sub_accounts", ["organization_id", "status"])

    _add_nullable_sub_account_fk_column(
        inspector=inspector,
        offline=offline,
        table_name="campaigns",
        fk_name="fk_campaigns_sub_account_id",
        index_name="ix_campaigns_sub_account_id",
    )
    _add_nullable_sub_account_fk_column(
        inspector=inspector,
        offline=offline,
        table_name="report_schedules",
        fk_name="fk_report_schedules_sub_account_id",
        index_name="ix_report_schedules_sub_account_id",
    )
    _add_nullable_sub_account_fk_column(
        inspector=inspector,
        offline=offline,
        table_name="provider_execution_metrics",
        fk_name="fk_provider_execution_metrics_sub_account_id",
        index_name="ix_provider_execution_metrics_sub_account_id",
    )


def downgrade() -> None:
    bind = op.get_bind()
    offline = context.is_offline_mode()
    inspector = None if offline else sa.inspect(bind)

    _drop_nullable_sub_account_fk_column(
        inspector=inspector,
        offline=offline,
        table_name="provider_execution_metrics",
        fk_name="fk_provider_execution_metrics_sub_account_id",
        index_name="ix_provider_execution_metrics_sub_account_id",
    )
    _drop_nullable_sub_account_fk_column(
        inspector=inspector,
        offline=offline,
        table_name="report_schedules",
        fk_name="fk_report_schedules_sub_account_id",
        index_name="ix_report_schedules_sub_account_id",
    )
    _drop_nullable_sub_account_fk_column(
        inspector=inspector,
        offline=offline,
        table_name="campaigns",
        fk_name="fk_campaigns_sub_account_id",
        index_name="ix_campaigns_sub_account_id",
    )

    if offline:
        op.drop_index("ix_sub_accounts_org_status", table_name="sub_accounts")
        op.drop_index("ix_sub_accounts_organization_id", table_name="sub_accounts")
        op.drop_table("sub_accounts")
        return

    tables = set(inspector.get_table_names())
    if "sub_accounts" in tables:
        indexes = {idx["name"] for idx in inspector.get_indexes("sub_accounts")}
        if "ix_sub_accounts_org_status" in indexes:
            op.drop_index("ix_sub_accounts_org_status", table_name="sub_accounts")
        if "ix_sub_accounts_organization_id" in indexes:
            op.drop_index("ix_sub_accounts_organization_id", table_name="sub_accounts")
        op.drop_table("sub_accounts")


def _add_nullable_sub_account_fk_column(
    *,
    inspector: sa.Inspector | None,
    offline: bool,
    table_name: str,
    fk_name: str,
    index_name: str,
) -> None:
    if offline:
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.add_column(sa.Column("sub_account_id", sa.String(length=36), nullable=True))
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.create_foreign_key(
                fk_name,
                "sub_accounts",
                ["sub_account_id"],
                ["id"],
                ondelete="SET NULL",
            )
        op.create_index(index_name, table_name, ["sub_account_id"])
        return

    columns = {column["name"] for column in inspector.get_columns(table_name)}
    if "sub_account_id" not in columns:
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.add_column(sa.Column("sub_account_id", sa.String(length=36), nullable=True))

    foreign_keys = {fk["name"] for fk in inspector.get_foreign_keys(table_name)}
    if fk_name not in foreign_keys:
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.create_foreign_key(
                fk_name,
                "sub_accounts",
                ["sub_account_id"],
                ["id"],
                ondelete="SET NULL",
            )

    indexes = {idx["name"] for idx in inspector.get_indexes(table_name)}
    if index_name not in indexes:
        op.create_index(index_name, table_name, ["sub_account_id"])


def _drop_nullable_sub_account_fk_column(
    *,
    inspector: sa.Inspector | None,
    offline: bool,
    table_name: str,
    fk_name: str,
    index_name: str,
) -> None:
    if offline:
        op.drop_index(index_name, table_name=table_name)
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.drop_constraint(fk_name, type_="foreignkey")
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.drop_column("sub_account_id")
        return

    columns = {column["name"] for column in inspector.get_columns(table_name)}
    if "sub_account_id" not in columns:
        return

    indexes = {idx["name"] for idx in inspector.get_indexes(table_name)}
    if index_name in indexes:
        op.drop_index(index_name, table_name=table_name)

    foreign_keys = {fk["name"] for fk in inspector.get_foreign_keys(table_name)}
    if fk_name in foreign_keys:
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.drop_constraint(fk_name, type_="foreignkey")

    with op.batch_alter_table(table_name) as batch_op:
        batch_op.drop_column("sub_account_id")

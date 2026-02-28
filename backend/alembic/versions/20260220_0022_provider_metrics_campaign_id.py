"""add campaign id to provider execution metrics

Revision ID: 20260220_0022
Revises: 20260220_0021
Create Date: 2026-02-20 16:45:00
"""

from __future__ import annotations

from alembic import context
from alembic import op
import sqlalchemy as sa


revision = "20260220_0022"
down_revision = "20260220_0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    offline = context.is_offline_mode()
    inspector = None if offline else sa.inspect(bind)

    if offline:
        with op.batch_alter_table("provider_execution_metrics") as batch_op:
            batch_op.add_column(sa.Column("campaign_id", sa.String(length=36), nullable=True))
        with op.batch_alter_table("provider_execution_metrics") as batch_op:
            batch_op.create_foreign_key(
                "fk_provider_execution_metrics_campaign_id",
                "campaigns",
                ["campaign_id"],
                ["id"],
                ondelete="SET NULL",
            )
        op.create_index(
            "ix_provider_execution_metrics_tenant_campaign_created_at",
            "provider_execution_metrics",
            ["tenant_id", "campaign_id", "created_at"],
        )
        return

    columns = {column["name"] for column in inspector.get_columns("provider_execution_metrics")}
    if "campaign_id" not in columns:
        with op.batch_alter_table("provider_execution_metrics") as batch_op:
            batch_op.add_column(sa.Column("campaign_id", sa.String(length=36), nullable=True))

    foreign_keys = {fk["name"] for fk in inspector.get_foreign_keys("provider_execution_metrics")}
    if "fk_provider_execution_metrics_campaign_id" not in foreign_keys:
        with op.batch_alter_table("provider_execution_metrics") as batch_op:
            batch_op.create_foreign_key(
                "fk_provider_execution_metrics_campaign_id",
                "campaigns",
                ["campaign_id"],
                ["id"],
                ondelete="SET NULL",
            )

    indexes = {idx["name"] for idx in inspector.get_indexes("provider_execution_metrics")}
    if "ix_provider_execution_metrics_tenant_campaign_created_at" not in indexes:
        op.create_index(
            "ix_provider_execution_metrics_tenant_campaign_created_at",
            "provider_execution_metrics",
            ["tenant_id", "campaign_id", "created_at"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    offline = context.is_offline_mode()
    inspector = None if offline else sa.inspect(bind)

    if offline:
        op.drop_index("ix_provider_execution_metrics_tenant_campaign_created_at", table_name="provider_execution_metrics")
        with op.batch_alter_table("provider_execution_metrics") as batch_op:
            batch_op.drop_constraint("fk_provider_execution_metrics_campaign_id", type_="foreignkey")
        with op.batch_alter_table("provider_execution_metrics") as batch_op:
            batch_op.drop_column("campaign_id")
        return

    columns = {column["name"] for column in inspector.get_columns("provider_execution_metrics")}
    if "campaign_id" not in columns:
        return

    indexes = {idx["name"] for idx in inspector.get_indexes("provider_execution_metrics")}
    if "ix_provider_execution_metrics_tenant_campaign_created_at" in indexes:
        op.drop_index("ix_provider_execution_metrics_tenant_campaign_created_at", table_name="provider_execution_metrics")

    foreign_keys = {fk["name"] for fk in inspector.get_foreign_keys("provider_execution_metrics")}
    if "fk_provider_execution_metrics_campaign_id" in foreign_keys:
        with op.batch_alter_table("provider_execution_metrics") as batch_op:
            batch_op.drop_constraint("fk_provider_execution_metrics_campaign_id", type_="foreignkey")

    with op.batch_alter_table("provider_execution_metrics") as batch_op:
        batch_op.drop_column("campaign_id")

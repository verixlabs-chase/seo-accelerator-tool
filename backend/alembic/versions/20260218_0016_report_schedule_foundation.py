"""add report schedule configuration table

Revision ID: 20260218_0016
Revises: 20260218_0015
Create Date: 2026-02-18 23:10:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260218_0016"
down_revision = "20260218_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "report_schedules",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("campaign_id", sa.String(length=36), sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cadence", sa.String(length=20), nullable=False, server_default="monthly"),
        sa.Column("timezone", sa.String(length=80), nullable=False, server_default="UTC"),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_status", sa.String(length=40), nullable=False, server_default="idle"),
    )
    op.create_index("ix_report_schedules_tenant_id", "report_schedules", ["tenant_id"])
    op.create_index("ix_report_schedules_campaign_id", "report_schedules", ["campaign_id"])
    op.create_index("ix_report_schedules_next_run_at", "report_schedules", ["next_run_at"])


def downgrade() -> None:
    op.drop_index("ix_report_schedules_next_run_at", table_name="report_schedules")
    op.drop_index("ix_report_schedules_campaign_id", table_name="report_schedules")
    op.drop_index("ix_report_schedules_tenant_id", table_name="report_schedules")
    op.drop_table("report_schedules")

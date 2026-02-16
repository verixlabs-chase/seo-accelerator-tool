"""sprint9 reporting foundation tables

Revision ID: 20260216_0009
Revises: 20260216_0008
Create Date: 2026-02-16 18:20:00
"""
from alembic import op
import sqlalchemy as sa


revision = "20260216_0009"
down_revision = "20260216_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "monthly_reports",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("campaign_id", sa.String(length=36), sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("month_number", sa.Integer(), nullable=False),
        sa.Column("report_status", sa.String(length=40), nullable=False, server_default="generated"),
        sa.Column("summary_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_monthly_reports_tenant_id", "monthly_reports", ["tenant_id"])
    op.create_index("ix_monthly_reports_campaign_id", "monthly_reports", ["campaign_id"])
    op.create_index("ix_monthly_reports_generated_at", "monthly_reports", ["generated_at"])

    op.create_table(
        "report_artifacts",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("campaign_id", sa.String(length=36), nullable=False),
        sa.Column("report_id", sa.String(length=36), sa.ForeignKey("monthly_reports.id", ondelete="CASCADE"), nullable=False),
        sa.Column("artifact_type", sa.String(length=40), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_report_artifacts_tenant_id", "report_artifacts", ["tenant_id"])
    op.create_index("ix_report_artifacts_campaign_id", "report_artifacts", ["campaign_id"])
    op.create_index("ix_report_artifacts_report_id", "report_artifacts", ["report_id"])
    op.create_index("ix_report_artifacts_created_at", "report_artifacts", ["created_at"])

    op.create_table(
        "report_delivery_events",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("campaign_id", sa.String(length=36), nullable=False),
        sa.Column("report_id", sa.String(length=36), sa.ForeignKey("monthly_reports.id", ondelete="CASCADE"), nullable=False),
        sa.Column("delivery_channel", sa.String(length=40), nullable=False, server_default="email"),
        sa.Column("delivery_status", sa.String(length=40), nullable=False, server_default="queued"),
        sa.Column("recipient", sa.String(length=320), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_report_delivery_events_tenant_id", "report_delivery_events", ["tenant_id"])
    op.create_index("ix_report_delivery_events_campaign_id", "report_delivery_events", ["campaign_id"])
    op.create_index("ix_report_delivery_events_report_id", "report_delivery_events", ["report_id"])
    op.create_index("ix_report_delivery_events_created_at", "report_delivery_events", ["created_at"])

    op.create_table(
        "report_template_versions",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("template_key", sa.String(length=120), nullable=False),
        sa.Column("version", sa.String(length=40), nullable=False),
        sa.Column("css_theme", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_report_template_versions_tenant_id", "report_template_versions", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_report_template_versions_tenant_id", table_name="report_template_versions")
    op.drop_table("report_template_versions")

    op.drop_index("ix_report_delivery_events_created_at", table_name="report_delivery_events")
    op.drop_index("ix_report_delivery_events_report_id", table_name="report_delivery_events")
    op.drop_index("ix_report_delivery_events_campaign_id", table_name="report_delivery_events")
    op.drop_index("ix_report_delivery_events_tenant_id", table_name="report_delivery_events")
    op.drop_table("report_delivery_events")

    op.drop_index("ix_report_artifacts_created_at", table_name="report_artifacts")
    op.drop_index("ix_report_artifacts_report_id", table_name="report_artifacts")
    op.drop_index("ix_report_artifacts_campaign_id", table_name="report_artifacts")
    op.drop_index("ix_report_artifacts_tenant_id", table_name="report_artifacts")
    op.drop_table("report_artifacts")

    op.drop_index("ix_monthly_reports_generated_at", table_name="monthly_reports")
    op.drop_index("ix_monthly_reports_campaign_id", table_name="monthly_reports")
    op.drop_index("ix_monthly_reports_tenant_id", table_name="monthly_reports")
    op.drop_table("monthly_reports")


"""add Google business profile intelligence storage

Revision ID: 20260805_0098
Revises: 20260805_0097
Create Date: 2026-08-05 10:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260805_0098"
down_revision = "20260805_0097"
branch_labels = None
depends_on = None


def _tenant_columns() -> list[sa.Column]:
    return [
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("campaign_id", sa.String(36), sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("business_location_id", sa.String(36), sa.ForeignKey("business_locations.id", ondelete="CASCADE"), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "google_business_profile_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("connection_id", sa.String(36), sa.ForeignKey("data_connections.id", ondelete="CASCADE"), nullable=False),
        *_tenant_columns(),
        sa.Column("external_resource_id", sa.String(120), nullable=False),
        sa.Column("profile_hash", sa.String(64), nullable=False),
        sa.Column("profile_data", sa.JSON(), nullable=False),
        sa.Column("audit_summary", sa.JSON(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("connection_id", "profile_hash", name="uq_gbp_snapshots_connection_hash"),
    )
    op.create_index("ix_gbp_snapshots_campaign_captured", "google_business_profile_snapshots", ["campaign_id", "captured_at"])

    op.create_table(
        "google_business_profile_daily_metrics",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("connection_id", sa.String(36), sa.ForeignKey("data_connections.id", ondelete="CASCADE"), nullable=False),
        *_tenant_columns(),
        sa.Column("metric_date", sa.Date(), nullable=False),
        sa.Column("metric_name", sa.String(80), nullable=False),
        sa.Column("metric_value", sa.Integer(), nullable=True),
        sa.Column("missing_reason", sa.String(255), nullable=True),
        sa.Column("source_name", sa.String(64), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("connection_id", "metric_date", "metric_name", name="uq_gbp_daily_metrics_connection_date_metric"),
    )
    op.create_index("ix_gbp_daily_metrics_campaign_date", "google_business_profile_daily_metrics", ["campaign_id", "metric_date"])

    op.create_table(
        "google_business_profile_search_keywords",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("connection_id", sa.String(36), sa.ForeignKey("data_connections.id", ondelete="CASCADE"), nullable=False),
        *_tenant_columns(),
        sa.Column("metric_month", sa.Date(), nullable=False),
        sa.Column("keyword", sa.String(500), nullable=False),
        sa.Column("impressions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_name", sa.String(64), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("connection_id", "metric_month", "keyword", name="uq_gbp_search_keywords_connection_month_keyword"),
    )
    op.create_index("ix_gbp_search_keywords_campaign_month", "google_business_profile_search_keywords", ["campaign_id", "metric_month"])

    for table in (
        "google_business_profile_snapshots",
        "google_business_profile_daily_metrics",
        "google_business_profile_search_keywords",
    ):
        for column in ("connection_id", "tenant_id", "organization_id", "campaign_id", "business_location_id"):
            op.create_index(f"ix_{table}_{column}", table, [column])

    op.create_index("ix_gbp_snapshots_captured_at", "google_business_profile_snapshots", ["captured_at"])
    for table in ("google_business_profile_daily_metrics", "google_business_profile_search_keywords"):
        date_column = "metric_date" if table.endswith("daily_metrics") else "metric_month"
        op.create_index(f"ix_{table}_{date_column}", table, [date_column])
    op.create_index("ix_gbp_daily_metrics_metric_name", "google_business_profile_daily_metrics", ["metric_name"])

    if op.get_bind().dialect.name == "postgresql":
        for table in (
            "google_business_profile_snapshots",
            "google_business_profile_daily_metrics",
            "google_business_profile_search_keywords",
        ):
            op.execute(sa.text(f"GRANT SELECT, INSERT, UPDATE ON TABLE public.{table} TO lsos_app"))
            op.execute(sa.text(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY"))
            op.execute(sa.text(
                f"CREATE POLICY lsos_tenant_isolation ON public.{table} FOR ALL TO lsos_app "
                "USING (current_setting('app.platform_access', true) = 'on' OR "
                "(tenant_id::text = current_setting('app.current_tenant_id', true) AND "
                "organization_id::text = current_setting('app.current_organization_id', true))) "
                "WITH CHECK (current_setting('app.platform_access', true) = 'on' OR "
                "(tenant_id::text = current_setting('app.current_tenant_id', true) AND "
                "organization_id::text = current_setting('app.current_organization_id', true)))"
            ))


def downgrade() -> None:
    op.drop_table("google_business_profile_search_keywords")
    op.drop_table("google_business_profile_daily_metrics")
    op.drop_table("google_business_profile_snapshots")

"""add website analytics detail facts and privacy-minimized form events

Revision ID: 20260812_0124
Revises: 20260812_0123
Create Date: 2026-08-12 18:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260812_0124"
down_revision = "20260812_0123"
branch_labels = None
depends_on = None


def _scope_columns() -> list[sa.Column]:
    return [
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("business_location_id", sa.String(36), nullable=False),
        sa.Column("campaign_id", sa.String(36), nullable=False),
    ]


def _scope_foreign_keys() -> list[sa.ForeignKeyConstraint]:
    return [
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["business_location_id"],
            ["business_locations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
    ]


def upgrade() -> None:
    op.create_table(
        "analytics_landing_page_daily_metrics",
        *_scope_columns(),
        sa.Column("metric_date", sa.Date(), nullable=False),
        sa.Column("landing_page", sa.Text(), nullable=False),
        sa.Column("dimension_hash", sa.String(64), nullable=False),
        sa.Column("sessions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("engaged_sessions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("key_events", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("deterministic_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        *_scope_foreign_keys(),
        sa.UniqueConstraint(
            "campaign_id",
            "metric_date",
            "dimension_hash",
            name="uq_analytics_landing_page_campaign_date_hash",
        ),
    )
    op.create_table(
        "analytics_traffic_source_daily_metrics",
        *_scope_columns(),
        sa.Column("metric_date", sa.Date(), nullable=False),
        sa.Column("source_medium", sa.String(500), nullable=False),
        sa.Column("dimension_hash", sa.String(64), nullable=False),
        sa.Column("sessions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("engaged_sessions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("key_events", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("deterministic_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        *_scope_foreign_keys(),
        sa.UniqueConstraint(
            "campaign_id",
            "metric_date",
            "dimension_hash",
            name="uq_analytics_traffic_source_campaign_date_hash",
        ),
    )
    op.create_table(
        "website_form_events",
        *_scope_columns(),
        sa.Column("data_connection_id", sa.String(36), nullable=False),
        sa.Column("event_id", sa.String(128), nullable=False),
        sa.Column("event_name", sa.String(40), nullable=False),
        sa.Column("website", sa.String(500), nullable=False),
        sa.Column("page_url", sa.Text(), nullable=False),
        sa.Column("form_id", sa.String(120), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        *_scope_foreign_keys(),
        sa.ForeignKeyConstraint(
            ["data_connection_id"],
            ["data_connections.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "data_connection_id",
            "event_id",
            name="uq_website_form_events_connection_event",
        ),
    )

    index_specs = {
        "analytics_landing_page_daily_metrics": (
            "tenant_id",
            "organization_id",
            "business_location_id",
            "campaign_id",
            "metric_date",
        ),
        "analytics_traffic_source_daily_metrics": (
            "tenant_id",
            "organization_id",
            "business_location_id",
            "campaign_id",
            "metric_date",
        ),
        "website_form_events": (
            "tenant_id",
            "organization_id",
            "business_location_id",
            "campaign_id",
            "data_connection_id",
        ),
    }
    for table, columns in index_specs.items():
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column])
    op.create_index(
        "ix_analytics_landing_page_campaign_date",
        "analytics_landing_page_daily_metrics",
        ["campaign_id", "metric_date"],
    )
    op.create_index(
        "ix_analytics_traffic_source_campaign_date",
        "analytics_traffic_source_daily_metrics",
        ["campaign_id", "metric_date"],
    )
    op.create_index(
        "ix_website_form_events_campaign_occurred",
        "website_form_events",
        ["campaign_id", "occurred_at"],
    )

    if op.get_bind().dialect.name == "postgresql":
        for table in index_specs:
            op.execute(
                sa.text(
                    f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.{table} TO lsos_app"
                )
            )
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
    op.drop_table("website_form_events")
    op.drop_table("analytics_traffic_source_daily_metrics")
    op.drop_table("analytics_landing_page_daily_metrics")

"""add governed directory listing discovery runs

Revision ID: 20260810_0107
Revises: 20260810_0106
Create Date: 2026-08-10 16:10:00.000000
"""

from __future__ import annotations

from datetime import UTC, datetime

from alembic import op
import sqlalchemy as sa


revision = "20260810_0107"
down_revision = "20260810_0106"
branch_labels = None
depends_on = None

PRICE_CARD_ID = "d7c1a1e2-f38a-46cb-b4d4-65bcddc15b01"


def upgrade() -> None:
    op.create_table(
        "directory_listing_discovery_runs",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("campaign_id", sa.String(36), nullable=False),
        sa.Column("business_location_id", sa.String(36), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("provider_name", sa.String(100), nullable=False),
        sa.Column("credential_owner", sa.String(20), nullable=False),
        sa.Column("radius_km", sa.Numeric(9, 2), nullable=False),
        sa.Column("result_limit", sa.Integer(), nullable=False),
        sa.Column("reservation_id", sa.String(36), nullable=True),
        sa.Column("estimated_cost", sa.Numeric(18, 8), nullable=False, server_default="0"),
        sa.Column("provider_reported_cost", sa.Numeric(18, 8), nullable=True),
        sa.Column("estimated_credit_units", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("result_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_code", sa.String(80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("requested_by_user_id", sa.String(36), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["business_location_id"], ["business_locations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["reservation_id"], ["cost_ledger_entries.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_dir_listing_discovery_org_idempotency",
        ),
        sa.CheckConstraint(
            "status in ('queued','running','completed','failed')",
            name="ck_dir_listing_discovery_status",
        ),
        sa.CheckConstraint(
            "credential_owner in ('platform','organization')",
            name="ck_dir_listing_discovery_credential_owner",
        ),
        sa.CheckConstraint(
            "result_limit >= 1 and result_limit <= 100",
            name="ck_dir_listing_discovery_result_limit",
        ),
    )
    for column in (
        "tenant_id",
        "organization_id",
        "campaign_id",
        "business_location_id",
        "status",
    ):
        op.create_index(
            f"ix_dir_listing_discovery_{column}",
            "directory_listing_discovery_runs",
            [column],
        )
    op.create_index(
        "ix_dir_listing_discovery_campaign_created",
        "directory_listing_discovery_runs",
        ["campaign_id", "created_at"],
    )

    price_cards = sa.table(
        "provider_price_cards",
        sa.column("id", sa.String),
        sa.column("provider_name", sa.String),
        sa.column("capability", sa.String),
        sa.column("operation", sa.String),
        sa.column("model_name", sa.String),
        sa.column("unit", sa.String),
        sa.column("unit_cost", sa.Numeric),
        sa.column("currency", sa.String),
        sa.column("version", sa.String),
        sa.column("source_url", sa.String),
        sa.column("effective_from", sa.DateTime(timezone=True)),
        sa.column("active", sa.Boolean),
    )
    op.bulk_insert(
        price_cards,
        [
            {
                "id": PRICE_CARD_ID,
                "provider_name": "dataforseo",
                "capability": "directory_listing_discovery",
                "operation": "business_listings_live_limit_20",
                "model_name": "",
                "unit": "search",
                "unit_cost": 0.0192,
                "currency": "USD",
                "version": "business-listings-2026-07-01-v1",
                "source_url": "https://dataforseo.com/pricing/business-data/business-listings-api",
                "effective_from": datetime(2026, 7, 1, tzinfo=UTC),
                "active": True,
            }
        ],
    )

    if op.get_bind().dialect.name == "postgresql":
        table = "directory_listing_discovery_runs"
        op.execute(sa.text(f"GRANT SELECT, INSERT, UPDATE ON TABLE public.{table} TO lsos_app"))
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
    op.execute(
        sa.text("DELETE FROM provider_price_cards WHERE id = :id").bindparams(id=PRICE_CARD_ID)
    )
    op.drop_table("directory_listing_discovery_runs")

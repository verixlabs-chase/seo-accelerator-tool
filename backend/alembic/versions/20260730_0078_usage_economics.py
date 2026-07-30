"""add usage economics ledger and margin controls

Revision ID: 20260730_0078
Revises: 20260730_0077
Create Date: 2026-07-30 13:15:00.000000
"""

from __future__ import annotations

from datetime import UTC, datetime

from alembic import op
import sqlalchemy as sa


revision = "20260730_0078"
down_revision = "20260730_0077"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("organizations") as batch_op:
        batch_op.drop_constraint("ck_organizations_plan_type", type_="check")
        batch_op.create_check_constraint(
            "ck_organizations_plan_type",
            "plan_type in "
            "('internal_anchor','standard','pro','solo','multi_location','enterprise')",
        )

    op.create_table(
        "provider_price_cards",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("provider_name", sa.String(length=80), nullable=False),
        sa.Column("capability", sa.String(length=80), nullable=False),
        sa.Column("operation", sa.String(length=120), nullable=False),
        sa.Column("model_name", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("version", sa.String(length=80), nullable=False),
        sa.Column("unit", sa.String(length=40), nullable=False),
        sa.Column("unit_cost", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("input_token_cost_per_million", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("cached_input_token_cost_per_million", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("output_token_cost_per_million", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="USD"),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("source_url", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider_name",
            "capability",
            "operation",
            "model_name",
            "version",
            name="uq_provider_price_card_identity",
        ),
    )
    op.create_index(
        "ix_provider_price_cards_lookup",
        "provider_price_cards",
        ["provider_name", "capability", "operation", "active", "effective_from"],
        unique=False,
    )

    op.create_table(
        "cost_ledger_entries",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("business_location_id", sa.String(length=36), nullable=True),
        sa.Column("campaign_id", sa.String(length=36), nullable=True),
        sa.Column("provider_name", sa.String(length=80), nullable=False),
        sa.Column("capability", sa.String(length=80), nullable=False),
        sa.Column("operation", sa.String(length=120), nullable=False),
        sa.Column("credential_owner", sa.String(length=20), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("unit", sa.String(length=40), nullable=False),
        sa.Column("estimated_cost", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("provider_reported_cost", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("budget_impact_cost", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="USD"),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("event_type", sa.String(length=24), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("reservation_id", sa.String(length=36), nullable=True),
        sa.Column("price_card_version", sa.String(length=80), nullable=False),
        sa.Column("plan_code", sa.String(length=40), nullable=False),
        sa.Column("plan_revenue_snapshot", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("model_name", sa.String(length=120), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("cached_input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("reconciled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["business_location_id"], ["business_locations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "credential_owner in ('platform','organization')",
            name="ck_cost_ledger_credential_owner",
        ),
        sa.CheckConstraint(
            "event_type in ('reservation','reconciliation','release')",
            name="ck_cost_ledger_event_type",
        ),
        sa.CheckConstraint(
            "status in ('reserved','reconciled','released')",
            name="ck_cost_ledger_status",
        ),
        sa.CheckConstraint("quantity >= 0", name="ck_cost_ledger_quantity_nonnegative"),
        sa.CheckConstraint("estimated_cost >= 0", name="ck_cost_ledger_estimated_nonnegative"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "idempotency_key",
            "event_type",
            name="uq_cost_ledger_org_key_event",
        ),
    )
    op.create_index(
        "ix_cost_ledger_org_created",
        "cost_ledger_entries",
        ["organization_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_cost_ledger_org_status",
        "cost_ledger_entries",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_index("ix_cost_ledger_reservation", "cost_ledger_entries", ["reservation_id"], unique=False)
    op.create_index(
        "ix_cost_ledger_provider_created",
        "cost_ledger_entries",
        ["provider_name", "capability", "created_at"],
        unique=False,
    )

    op.create_table(
        "organization_cost_allocations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("revenue_override", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("hosting_cost", sa.Numeric(precision=18, scale=2), nullable=False, server_default="0"),
        sa.Column("storage_cost", sa.Numeric(precision=18, scale=2), nullable=False, server_default="0"),
        sa.Column("email_cost", sa.Numeric(precision=18, scale=2), nullable=False, server_default="0"),
        sa.Column("support_cost", sa.Numeric(precision=18, scale=2), nullable=False, server_default="0"),
        sa.Column("other_cost", sa.Numeric(precision=18, scale=2), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="USD"),
        sa.Column("source", sa.String(length=80), nullable=False, server_default="operator"),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.CheckConstraint("hosting_cost >= 0", name="ck_org_cost_hosting_nonnegative"),
        sa.CheckConstraint("storage_cost >= 0", name="ck_org_cost_storage_nonnegative"),
        sa.CheckConstraint("email_cost >= 0", name="ck_org_cost_email_nonnegative"),
        sa.CheckConstraint("support_cost >= 0", name="ck_org_cost_support_nonnegative"),
        sa.CheckConstraint("other_cost >= 0", name="ck_org_cost_other_nonnegative"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "period_start",
            "version",
            name="uq_org_cost_allocation_period_version",
        ),
    )
    op.create_index(
        "ix_org_cost_allocations_period",
        "organization_cost_allocations",
        ["organization_id", "period_start", "version"],
        unique=False,
    )

    price_cards = sa.table(
        "provider_price_cards",
        sa.column("id", sa.String),
        sa.column("provider_name", sa.String),
        sa.column("capability", sa.String),
        sa.column("operation", sa.String),
        sa.column("model_name", sa.String),
        sa.column("version", sa.String),
        sa.column("unit", sa.String),
        sa.column("unit_cost", sa.Numeric),
        sa.column("currency", sa.String),
        sa.column("effective_from", sa.DateTime(timezone=True)),
        sa.column("active", sa.Boolean),
        sa.column("source_url", sa.String),
    )
    op.bulk_insert(
        price_cards,
        [
            {
                "id": "b162eb24-d08e-4f00-87f8-fb799cbb2a73",
                "provider_name": "dataforseo",
                "capability": "rank_tracking",
                "operation": "google_organic_live_advanced",
                "model_name": "",
                "version": "dataforseo-google-organic-2026-07-30-v1",
                "unit": "serp_page",
                "unit_cost": 0.002,
                "currency": "USD",
                "effective_from": datetime(2026, 7, 30, tzinfo=UTC),
                "active": True,
                "source_url": "https://dataforseo.com/pricing/google-serp/google-organic-serp-api",
            }
        ],
    )

    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            sa.text(
                """
                ALTER TABLE public.cost_ledger_entries ENABLE ROW LEVEL SECURITY;
                DROP POLICY IF EXISTS lsos_tenant_isolation ON public.cost_ledger_entries;
                CREATE POLICY lsos_tenant_isolation ON public.cost_ledger_entries
                    FOR ALL TO lsos_app
                    USING (
                        current_setting('app.platform_access', true) = 'on'
                        OR organization_id::text =
                            current_setting('app.current_organization_id', true)
                    )
                    WITH CHECK (
                        current_setting('app.platform_access', true) = 'on'
                        OR organization_id::text =
                            current_setting('app.current_organization_id', true)
                    );

                ALTER TABLE public.organization_cost_allocations ENABLE ROW LEVEL SECURITY;
                DROP POLICY IF EXISTS lsos_tenant_isolation ON public.organization_cost_allocations;
                CREATE POLICY lsos_tenant_isolation ON public.organization_cost_allocations
                    FOR ALL TO lsos_app
                    USING (
                        current_setting('app.platform_access', true) = 'on'
                        OR organization_id::text =
                            current_setting('app.current_organization_id', true)
                    )
                    WITH CHECK (
                        current_setting('app.platform_access', true) = 'on'
                        OR organization_id::text =
                            current_setting('app.current_organization_id', true)
                    );

                CREATE OR REPLACE FUNCTION public.lsos_prevent_cost_ledger_mutation()
                RETURNS trigger
                LANGUAGE plpgsql
                AS $$
                BEGIN
                    RAISE EXCEPTION 'cost_ledger_entries is append-only';
                END;
                $$;

                DROP TRIGGER IF EXISTS trg_cost_ledger_append_only
                    ON public.cost_ledger_entries;
                CREATE TRIGGER trg_cost_ledger_append_only
                    BEFORE UPDATE OR DELETE ON public.cost_ledger_entries
                    FOR EACH ROW
                    EXECUTE FUNCTION public.lsos_prevent_cost_ledger_mutation();
                """
            )
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            sa.text(
                """
                DROP TRIGGER IF EXISTS trg_cost_ledger_append_only
                    ON public.cost_ledger_entries;
                DROP FUNCTION IF EXISTS public.lsos_prevent_cost_ledger_mutation();
                DROP POLICY IF EXISTS lsos_tenant_isolation ON public.organization_cost_allocations;
                ALTER TABLE public.organization_cost_allocations DISABLE ROW LEVEL SECURITY;
                DROP POLICY IF EXISTS lsos_tenant_isolation ON public.cost_ledger_entries;
                ALTER TABLE public.cost_ledger_entries DISABLE ROW LEVEL SECURITY;
                """
            )
        )

    op.drop_index("ix_org_cost_allocations_period", table_name="organization_cost_allocations")
    op.drop_table("organization_cost_allocations")
    op.drop_index("ix_cost_ledger_provider_created", table_name="cost_ledger_entries")
    op.drop_index("ix_cost_ledger_reservation", table_name="cost_ledger_entries")
    op.drop_index("ix_cost_ledger_org_status", table_name="cost_ledger_entries")
    op.drop_index("ix_cost_ledger_org_created", table_name="cost_ledger_entries")
    op.drop_table("cost_ledger_entries")
    op.drop_index("ix_provider_price_cards_lookup", table_name="provider_price_cards")
    op.drop_table("provider_price_cards")
    with op.batch_alter_table("organizations") as batch_op:
        batch_op.drop_constraint("ck_organizations_plan_type", type_="check")
        batch_op.create_check_constraint(
            "ck_organizations_plan_type",
            "plan_type in ('internal_anchor','standard','enterprise')",
        )

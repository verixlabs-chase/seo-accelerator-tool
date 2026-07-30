"""add governed AI runtime audit persistence

Revision ID: 20260730_0080
Revises: 20260730_0079
Create Date: 2026-07-30 20:30:00.000000
"""

from __future__ import annotations

from datetime import UTC, datetime

from alembic import op
import sqlalchemy as sa


revision = "20260730_0080"
down_revision = "20260730_0079"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "governed_ai_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("campaign_id", sa.String(length=36), nullable=False),
        sa.Column("business_location_id", sa.String(length=36), nullable=True),
        sa.Column("requested_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("feature", sa.String(length=80), nullable=False),
        sa.Column("provider_name", sa.String(length=80), nullable=False),
        sa.Column("model_name", sa.String(length=120), nullable=False),
        sa.Column("prompt_template_version", sa.String(length=80), nullable=False),
        sa.Column("lexicon_id", sa.String(length=120), nullable=False),
        sa.Column("lexicon_version", sa.String(length=80), nullable=False),
        sa.Column("context_hash", sa.String(length=64), nullable=False),
        sa.Column("prompt_hash", sa.String(length=64), nullable=False),
        sa.Column("response_hash", sa.String(length=64), nullable=True),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("provider_state", sa.String(length=40), nullable=False),
        sa.Column("selected_action_id", sa.String(length=160), nullable=True),
        sa.Column(
            "allowed_action_ids",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column(
            "evidence_refs",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column(
            "output_payload",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "estimated_cost",
            sa.Numeric(precision=18, scale=8),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "reconciled_cost",
            sa.Numeric(precision=18, scale=8),
            nullable=False,
            server_default="0",
        ),
        sa.Column("cost_reservation_id", sa.String(length=36), nullable=True),
        sa.Column("price_card_version", sa.String(length=80), nullable=True),
        sa.Column("provider_request_id", sa.String(length=160), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(length=120), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            "status in ('running','validated','fallback','rejected','failed')",
            name="ck_governed_ai_runs_status",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["campaign_id"],
            ["campaigns.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["business_location_id"],
            ["business_locations.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["cost_reservation_id"],
            ["cost_ledger_entries.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_governed_ai_runs_org_idempotency",
        ),
    )
    for column in (
        "tenant_id",
        "organization_id",
        "campaign_id",
        "business_location_id",
        "created_at",
    ):
        op.create_index(
            f"ix_governed_ai_runs_{column}",
            "governed_ai_runs",
            [column],
        )
    op.create_index(
        "ix_governed_ai_runs_campaign_created",
        "governed_ai_runs",
        ["campaign_id", "feature", "created_at"],
    )
    op.create_index(
        "ix_governed_ai_runs_org_status",
        "governed_ai_runs",
        ["organization_id", "status", "created_at"],
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
        sa.column("input_token_cost_per_million", sa.Numeric),
        sa.column("cached_input_token_cost_per_million", sa.Numeric),
        sa.column("output_token_cost_per_million", sa.Numeric),
        sa.column("currency", sa.String),
        sa.column("effective_from", sa.DateTime(timezone=True)),
        sa.column("active", sa.Boolean),
        sa.column("source_url", sa.String),
    )
    op.bulk_insert(
        price_cards,
        [
            {
                "id": "a480c5c4-531b-4b5c-b0ba-5679c88b0080",
                "provider_name": "mistral",
                "capability": "governed_ai",
                "operation": "intelligence_brief",
                "model_name": "mistral-small-2603",
                "version": "mistral-small-4-2026-03-v1",
                "unit": "request",
                "unit_cost": 0,
                "input_token_cost_per_million": 0.15,
                "cached_input_token_cost_per_million": None,
                "output_token_cost_per_million": 0.60,
                "currency": "USD",
                "effective_from": datetime(2026, 3, 16, tzinfo=UTC),
                "active": True,
                "source_url": (
                    "https://docs.mistral.ai/models/model-cards/"
                    "mistral-small-4-0-26-03"
                ),
            }
        ],
    )

    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            sa.text(
                """
                GRANT SELECT, INSERT, UPDATE, DELETE
                    ON TABLE public.governed_ai_runs TO lsos_app;
                ALTER TABLE public.governed_ai_runs ENABLE ROW LEVEL SECURITY;
                DROP POLICY IF EXISTS lsos_tenant_isolation
                    ON public.governed_ai_runs;
                CREATE POLICY lsos_tenant_isolation
                    ON public.governed_ai_runs
                    FOR ALL TO lsos_app
                    USING (
                        current_setting('app.platform_access', true) = 'on'
                        OR (
                            tenant_id::text =
                                current_setting('app.current_tenant_id', true)
                            AND organization_id::text =
                                current_setting('app.current_organization_id', true)
                        )
                    )
                    WITH CHECK (
                        current_setting('app.platform_access', true) = 'on'
                        OR (
                            tenant_id::text =
                                current_setting('app.current_tenant_id', true)
                            AND organization_id::text =
                                current_setting('app.current_organization_id', true)
                        )
                    );
                """
            )
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            sa.text(
                """
                DROP POLICY IF EXISTS lsos_tenant_isolation
                    ON public.governed_ai_runs;
                ALTER TABLE public.governed_ai_runs DISABLE ROW LEVEL SECURITY;
                """
            )
        )
    op.execute(
        sa.text(
            """
            DELETE FROM provider_price_cards
            WHERE version = 'mistral-small-4-2026-03-v1'
            """
        )
    )
    op.drop_index(
        "ix_governed_ai_runs_org_status",
        table_name="governed_ai_runs",
    )
    op.drop_index(
        "ix_governed_ai_runs_campaign_created",
        table_name="governed_ai_runs",
    )
    for column in (
        "created_at",
        "business_location_id",
        "campaign_id",
        "organization_id",
        "tenant_id",
    ):
        op.drop_index(
            f"ix_governed_ai_runs_{column}",
            table_name="governed_ai_runs",
        )
    op.drop_table("governed_ai_runs")

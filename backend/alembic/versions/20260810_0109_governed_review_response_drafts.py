"""add governed review response drafts

Revision ID: 20260810_0109
Revises: 20260810_0108
Create Date: 2026-08-10 19:15:00.000000
"""

from __future__ import annotations

from datetime import UTC, datetime

from alembic import op
import sqlalchemy as sa


revision = "20260810_0109"
down_revision = "20260810_0108"
branch_labels = None
depends_on = None

PRICE_CARD_ID = "ce1f20a0-4517-4ca2-9d9b-8882be5f0109"
PRICE_CARD_VERSION = "mistral-small-4-review-response-2026-03-v1"


def _price_cards() -> sa.TableClause:
    return sa.table(
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
        sa.column("effective_to", sa.DateTime(timezone=True)),
        sa.column("active", sa.Boolean),
        sa.column("source_url", sa.String),
    )


def upgrade() -> None:
    op.create_table(
        "reputation_response_policies",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("version", sa.String(80), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="active"),
        sa.Column("mode", sa.String(32), nullable=False, server_default="draft_only"),
        sa.Column("rules", sa.JSON(), nullable=False),
        sa.Column("rules_hash", sa.String(64), nullable=False),
        sa.Column("created_by_user_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint(
            "organization_id",
            "version",
            name="uq_reputation_response_policies_org_version",
        ),
        sa.CheckConstraint(
            "status in ('active','inactive')",
            name="ck_reputation_response_policies_status",
        ),
    )
    op.create_table(
        "reputation_response_drafts",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("campaign_id", sa.String(36), nullable=False),
        sa.Column("business_location_id", sa.String(36), nullable=False),
        sa.Column("review_id", sa.String(36), nullable=False),
        sa.Column("policy_id", sa.String(36), nullable=False),
        sa.Column("governed_ai_run_id", sa.String(36), nullable=True),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("risk_class", sa.String(24), nullable=False),
        sa.Column("sensitive_topics", sa.JSON(), nullable=False),
        sa.Column("policy_version", sa.String(80), nullable=False),
        sa.Column("policy_snapshot", sa.JSON(), nullable=False),
        sa.Column("review_snapshot", sa.JSON(), nullable=False),
        sa.Column("evidence_refs", sa.JSON(), nullable=False),
        sa.Column("draft_text", sa.Text(), nullable=True),
        sa.Column("approved_text", sa.Text(), nullable=True),
        sa.Column("human_reason", sa.Text(), nullable=True),
        sa.Column("reviewed_by_user_id", sa.String(36), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["business_location_id"], ["business_locations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["review_id"], ["reputation_reviews.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["policy_id"], ["reputation_response_policies.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["governed_ai_run_id"], ["governed_ai_runs.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_reputation_response_drafts_org_idempotency",
        ),
        sa.CheckConstraint(
            "status in ('human_required','ready_for_review','approved','rejected','unavailable')",
            name="ck_reputation_response_drafts_status",
        ),
        sa.CheckConstraint(
            "risk_class in ('standard','sensitive')",
            name="ck_reputation_response_drafts_risk_class",
        ),
    )
    for table, columns in {
        "reputation_response_policies": ("tenant_id", "organization_id", "status"),
        "reputation_response_drafts": (
            "tenant_id",
            "organization_id",
            "campaign_id",
            "business_location_id",
            "review_id",
            "policy_id",
            "status",
            "created_at",
        ),
    }.items():
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column])
    op.create_index(
        "ix_reputation_response_policies_org_status",
        "reputation_response_policies",
        ["organization_id", "status"],
    )
    op.create_index(
        "ix_reputation_response_drafts_review_created",
        "reputation_response_drafts",
        ["review_id", "created_at"],
    )
    op.create_index(
        "ix_reputation_response_drafts_campaign_status",
        "reputation_response_drafts",
        ["campaign_id", "status"],
    )

    price_cards = _price_cards()
    op.get_bind().execute(
        price_cards.insert().values(
            id=PRICE_CARD_ID,
            provider_name="mistral",
            capability="governed_ai",
            operation="review_response_draft",
            model_name="mistral-small-2603",
            version=PRICE_CARD_VERSION,
            unit="request",
            unit_cost=0,
            input_token_cost_per_million=0.15,
            cached_input_token_cost_per_million=None,
            output_token_cost_per_million=0.60,
            currency="USD",
            effective_from=datetime(2026, 3, 16, tzinfo=UTC),
            effective_to=None,
            active=True,
            source_url="https://docs.mistral.ai/models/model-cards/mistral-small-4-0-26-03",
        )
    )

    if op.get_bind().dialect.name == "postgresql":
        for table in ("reputation_response_policies", "reputation_response_drafts"):
            op.execute(
                sa.text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.{table} TO lsos_app")
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
    price_cards = _price_cards()
    op.get_bind().execute(
        price_cards.delete().where(
            sa.and_(
                price_cards.c.provider_name == "mistral",
                price_cards.c.capability == "governed_ai",
                price_cards.c.operation == "review_response_draft",
                price_cards.c.model_name == "mistral-small-2603",
                price_cards.c.version == PRICE_CARD_VERSION,
            )
        )
    )
    op.drop_table("reputation_response_drafts")
    op.drop_table("reputation_response_policies")

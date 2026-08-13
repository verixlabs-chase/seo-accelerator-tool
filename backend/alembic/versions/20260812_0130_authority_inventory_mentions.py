"""add bounded authority inventory and verified unlinked mentions

Revision ID: 20260812_0130
Revises: 20260812_0129
Create Date: 2026-08-12 23:58:00.000000
"""

from __future__ import annotations

from datetime import UTC, datetime

from alembic import op
import sqlalchemy as sa


revision = "20260812_0130"
down_revision = "20260812_0129"
branch_labels = None
depends_on = None


PRICE_CARD_ID = "6a130b27-1f02-4f32-92a1-1b150e597130"


def upgrade() -> None:
    op.create_table(
        "authority_inventory_runs",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("campaign_id", sa.String(36), nullable=False),
        sa.Column("business_location_id", sa.String(36), nullable=True),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("owner_domain", sa.String(320), nullable=False),
        sa.Column("business_name", sa.String(255), nullable=False),
        sa.Column("link_limit", sa.Integer(), nullable=False),
        sa.Column("mention_limit", sa.Integer(), nullable=False),
        sa.Column("source_kind", sa.String(40), nullable=False),
        sa.Column("reservation_id", sa.String(36), nullable=True),
        sa.Column("provider_reported_cost", sa.Numeric(18, 8), nullable=True),
        sa.Column("link_count", sa.Integer(), nullable=False),
        sa.Column("mention_candidate_count", sa.Integer(), nullable=False),
        sa.Column("unlinked_mention_count", sa.Integer(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status in ('running','complete','partial','failed')",
            name="ck_authority_inventory_runs_status",
        ),
        sa.CheckConstraint(
            "link_limit >= 1 and link_limit <= 1000",
            name="ck_authority_inventory_runs_link_limit",
        ),
        sa.CheckConstraint(
            "mention_limit >= 1 and mention_limit <= 100",
            name="ck_authority_inventory_runs_mention_limit",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["business_location_id"], ["business_locations.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["reservation_id"], ["cost_ledger_entries.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_authority_inventory_runs_org_idempotency",
        ),
    )
    for column in (
        "tenant_id",
        "organization_id",
        "campaign_id",
        "business_location_id",
        "status",
        "created_at",
    ):
        op.create_index(
            f"ix_authority_inventory_runs_{column}", "authority_inventory_runs", [column]
        )
    op.create_index(
        "ix_authority_inventory_runs_campaign_created",
        "authority_inventory_runs",
        ["campaign_id", "created_at"],
    )

    op.create_table(
        "authority_inventory_links",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("campaign_id", sa.String(36), nullable=False),
        sa.Column("run_id", sa.String(36), nullable=False),
        sa.Column("referring_domain", sa.String(320), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("source_page_title", sa.Text(), nullable=True),
        sa.Column("target_url", sa.Text(), nullable=False),
        sa.Column("link_type", sa.String(40), nullable=True),
        sa.Column("dofollow", sa.Boolean(), nullable=False),
        sa.Column("anchor", sa.Text(), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["authority_inventory_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "run_id",
            "source_url",
            "target_url",
            name="uq_authority_inventory_links_run_source_target",
        ),
    )
    for column in (
        "tenant_id",
        "organization_id",
        "campaign_id",
        "run_id",
        "referring_domain",
        "observed_at",
    ):
        op.create_index(
            f"ix_authority_inventory_links_{column}", "authority_inventory_links", [column]
        )
    op.create_index(
        "ix_authority_inventory_links_campaign_observed",
        "authority_inventory_links",
        ["campaign_id", "observed_at"],
    )

    op.create_table(
        "authority_unlinked_mentions",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("campaign_id", sa.String(36), nullable=False),
        sa.Column("run_id", sa.String(36), nullable=False),
        sa.Column("referring_domain", sa.String(320), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("source_page_title", sa.Text(), nullable=True),
        sa.Column("snippet", sa.Text(), nullable=True),
        sa.Column("mentioned_name", sa.String(255), nullable=False),
        sa.Column("relevance_classification", sa.String(32), nullable=False),
        sa.Column("matched_services", sa.JSON(), nullable=False),
        sa.Column("matched_service_areas", sa.JSON(), nullable=False),
        sa.Column("relevance_reasons", sa.JSON(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "relevance_classification in "
            "('service_and_area_match','service_match','area_match','needs_review')",
            name="ck_authority_unlinked_mentions_relevance_classification",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["authority_inventory_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "run_id", "source_url", name="uq_authority_unlinked_mentions_run_source"
        ),
    )
    for column in (
        "tenant_id",
        "organization_id",
        "campaign_id",
        "run_id",
        "referring_domain",
        "relevance_classification",
        "observed_at",
    ):
        op.create_index(
            f"ix_authority_unlinked_mentions_{column}",
            "authority_unlinked_mentions",
            [column],
        )
    op.create_index(
        "ix_authority_unlinked_mentions_campaign_observed",
        "authority_unlinked_mentions",
        ["campaign_id", "observed_at"],
    )

    with op.batch_alter_table("authority_outreach_drafts") as batch_op:
        batch_op.drop_constraint("ck_authority_outreach_drafts_source_type", type_="check")
        batch_op.create_check_constraint(
            "ck_authority_outreach_drafts_source_type",
            "source_type in ('competitor_gap','lost_link','unlinked_mention')",
        )

    cards = sa.table(
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
        cards,
        [
            {
                "id": PRICE_CARD_ID,
                "provider_name": "dataforseo",
                "capability": "authority_research",
                "operation": "inventory_and_mentions_live_limit_50_10",
                "model_name": "",
                "version": "authority-inventory-pricing-2026-08-12-v1",
                "unit": "up_to_three_bounded_live_requests",
                "unit_cost": 0.08,
                "currency": "USD",
                "effective_from": datetime(2026, 8, 12, tzinfo=UTC),
                "active": True,
                "source_url": "https://dataforseo.com/pricing",
            }
        ],
    )


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM provider_price_cards WHERE id = :id").bindparams(id=PRICE_CARD_ID)
    )
    with op.batch_alter_table("authority_outreach_drafts") as batch_op:
        batch_op.drop_constraint("ck_authority_outreach_drafts_source_type", type_="check")
        batch_op.create_check_constraint(
            "ck_authority_outreach_drafts_source_type",
            "source_type in ('competitor_gap','lost_link')",
        )
    op.drop_table("authority_unlinked_mentions")
    op.drop_table("authority_inventory_links")
    op.drop_table("authority_inventory_runs")

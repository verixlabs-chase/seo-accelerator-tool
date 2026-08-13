"""add bounded authority link-gap research

Revision ID: 20260812_0128
Revises: 20260812_0127
Create Date: 2026-08-12 23:00:00.000000
"""

from __future__ import annotations

from datetime import UTC, datetime

from alembic import op
import sqlalchemy as sa


revision = "20260812_0128"
down_revision = "20260812_0127"
branch_labels = None
depends_on = None

PRICE_CARD_ID = "8f21edb8-fafb-4d3e-8ff6-b7e240d3b128"
LINK_CHANGE_PRICE_CARD_ID = "b95af82a-cd08-4ad3-9db3-24245ea16f9c"


def upgrade() -> None:
    op.create_table(
        "authority_gap_research_runs",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("campaign_id", sa.String(36), nullable=False),
        sa.Column("business_location_id", sa.String(36), nullable=True),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("owner_domain", sa.String(320), nullable=False),
        sa.Column("competitors", sa.JSON(), nullable=False),
        sa.Column("result_limit", sa.Integer(), nullable=False),
        sa.Column("source_kind", sa.String(40), nullable=False),
        sa.Column("reservation_id", sa.String(36), nullable=True),
        sa.Column("provider_reported_cost", sa.Numeric(18, 8), nullable=True),
        sa.Column("result_count", sa.Integer(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status in ('running','complete','partial','failed')",
            name="ck_authority_gap_runs_status",
        ),
        sa.CheckConstraint(
            "result_limit >= 1 and result_limit <= 1000",
            name="ck_authority_gap_runs_result_limit",
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
            name="uq_authority_gap_runs_org_idempotency",
        ),
    )
    op.create_index(
        "ix_authority_gap_runs_campaign_created",
        "authority_gap_research_runs",
        ["campaign_id", "created_at"],
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
            f"ix_authority_gap_research_runs_{column}",
            "authority_gap_research_runs",
            [column],
        )

    op.create_table(
        "authority_link_gaps",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("campaign_id", sa.String(36), nullable=False),
        sa.Column("run_id", sa.String(36), nullable=False),
        sa.Column("referring_domain", sa.String(320), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("source_page_title", sa.Text(), nullable=True),
        sa.Column("competitor_matches", sa.JSON(), nullable=False),
        sa.Column("relevance_classification", sa.String(32), nullable=False),
        sa.Column("matched_services", sa.JSON(), nullable=False),
        sa.Column("matched_service_areas", sa.JSON(), nullable=False),
        sa.Column("relevance_reasons", sa.JSON(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["authority_gap_research_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "relevance_classification in "
            "('service_and_area_match','service_match','area_match','needs_review')",
            name="ck_authority_link_gaps_relevance_classification",
        ),
        sa.UniqueConstraint("run_id", "source_url", name="uq_authority_link_gaps_run_source"),
    )
    op.create_index(
        "ix_authority_link_gaps_campaign_observed",
        "authority_link_gaps",
        ["campaign_id", "observed_at"],
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
            f"ix_authority_link_gaps_{column}",
            "authority_link_gaps",
            [column],
        )

    op.create_table(
        "authority_link_change_runs",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("campaign_id", sa.String(36), nullable=False),
        sa.Column("business_location_id", sa.String(36), nullable=True),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("owner_domain", sa.String(320), nullable=False),
        sa.Column("result_limit_per_state", sa.Integer(), nullable=False),
        sa.Column("source_kind", sa.String(40), nullable=False),
        sa.Column("reservation_id", sa.String(36), nullable=True),
        sa.Column("provider_reported_cost", sa.Numeric(18, 8), nullable=True),
        sa.Column("new_count", sa.Integer(), nullable=False),
        sa.Column("lost_count", sa.Integer(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status in ('running','complete','partial','failed')",
            name="ck_authority_link_change_runs_status",
        ),
        sa.CheckConstraint(
            "result_limit_per_state >= 1 and result_limit_per_state <= 500",
            name="ck_authority_link_change_runs_limit",
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
            name="uq_authority_link_change_runs_org_idempotency",
        ),
    )
    op.create_index(
        "ix_authority_link_change_runs_campaign_created",
        "authority_link_change_runs",
        ["campaign_id", "created_at"],
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
            f"ix_authority_link_change_runs_{column}",
            "authority_link_change_runs",
            [column],
        )

    op.create_table(
        "authority_link_changes",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("campaign_id", sa.String(36), nullable=False),
        sa.Column("run_id", sa.String(36), nullable=False),
        sa.Column("change_state", sa.String(12), nullable=False),
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
        sa.CheckConstraint(
            "change_state in ('new','lost')",
            name="ck_authority_link_changes_state",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["authority_link_change_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "run_id",
            "change_state",
            "source_url",
            "target_url",
            name="uq_authority_link_changes_run_state_source_target",
        ),
    )
    op.create_index(
        "ix_authority_link_changes_campaign_observed",
        "authority_link_changes",
        ["campaign_id", "observed_at"],
    )
    for column in (
        "tenant_id",
        "organization_id",
        "campaign_id",
        "run_id",
        "change_state",
        "referring_domain",
        "observed_at",
    ):
        op.create_index(
            f"ix_authority_link_changes_{column}",
            "authority_link_changes",
            [column],
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
                "operation": "page_intersection_live_limit_25",
                "model_name": "",
                "version": "backlinks-pricing-2026-08-12-v1",
                "unit": "request_up_to_25_rows",
                "unit_cost": 0.0249,
                "currency": "USD",
                "effective_from": datetime(2026, 8, 12, tzinfo=UTC),
                "active": True,
                "source_url": "https://dataforseo.com/pricing/backlinks/backlinks",
            },
            {
                "id": LINK_CHANGE_PRICE_CARD_ID,
                "provider_name": "dataforseo",
                "capability": "authority_research",
                "operation": "backlink_changes_live_limit_12_each",
                "model_name": "",
                "version": "backlinks-pricing-2026-08-12-v1",
                "unit": "two_requests_up_to_24_rows",
                "unit_cost": 0.048864,
                "currency": "USD",
                "effective_from": datetime(2026, 8, 12, tzinfo=UTC),
                "active": True,
                "source_url": "https://dataforseo.com/pricing/backlinks/backlinks",
            },
        ],
    )


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM provider_price_cards WHERE id = :id").bindparams(
            id=LINK_CHANGE_PRICE_CARD_ID
        )
    )
    op.execute(
        sa.text("DELETE FROM provider_price_cards WHERE id = :id").bindparams(id=PRICE_CARD_ID)
    )
    op.drop_table("authority_link_changes")
    op.drop_table("authority_link_change_runs")
    op.drop_table("authority_link_gaps")
    op.drop_table("authority_gap_research_runs")

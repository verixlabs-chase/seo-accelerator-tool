"""add local keyword discovery runs and suggestions

Revision ID: 20260803_0086
Revises: 20260803_0085
Create Date: 2026-08-03 22:30:00.000000
"""

from __future__ import annotations

from datetime import UTC, datetime

from alembic import op
import sqlalchemy as sa


revision = "20260803_0086"
down_revision = "20260803_0085"
branch_labels = None
depends_on = None


PRICE_CARD_IDS = (
    "fd0f372b-56ef-43f8-b866-a6cb3d69b1f1",
    "3c646e87-8d5c-46b9-a1d8-7b91d62fb979",
    "375a86c2-54f5-45b4-9008-e2d9e4f29924",
)


def upgrade() -> None:
    op.create_table(
        "keyword_research_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("campaign_id", sa.String(length=36), nullable=False),
        sa.Column("business_location_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("location_name", sa.String(length=255), nullable=False),
        sa.Column("language_code", sa.String(length=12), nullable=False),
        sa.Column("sources", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("warnings", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("suggestion_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("provider_reported_cost", sa.Numeric(18, 8), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status in ('running','complete','partial','unavailable')",
            name="ck_keyword_research_runs_status",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["business_location_id"], ["business_locations.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in (
        "tenant_id",
        "organization_id",
        "campaign_id",
        "business_location_id",
        "created_at",
    ):
        op.create_index(f"ix_keyword_research_runs_{column}", "keyword_research_runs", [column])
    op.create_index(
        "ix_keyword_research_runs_campaign_created",
        "keyword_research_runs",
        ["campaign_id", "created_at"],
    )

    op.create_table(
        "keyword_research_suggestions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("campaign_id", sa.String(length=36), nullable=False),
        sa.Column("business_location_id", sa.String(length=36), nullable=True),
        sa.Column("keyword", sa.String(length=255), nullable=False),
        sa.Column("normalized_keyword", sa.String(length=255), nullable=False),
        sa.Column("source_types", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("evidence", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("search_volume", sa.Integer(), nullable=True),
        sa.Column("cpc", sa.Numeric(18, 4), nullable=True),
        sa.Column("competition", sa.Float(), nullable=True),
        sa.Column("competition_level", sa.String(length=24), nullable=True),
        sa.Column("keyword_difficulty", sa.Integer(), nullable=True),
        sa.Column("monthly_searches", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("current_position", sa.Float(), nullable=True),
        sa.Column("gsc_clicks", sa.Float(), nullable=True),
        sa.Column("gsc_impressions", sa.Float(), nullable=True),
        sa.Column("gsc_position", sa.Float(), nullable=True),
        sa.Column("intent", sa.String(length=40), nullable=False),
        sa.Column("opportunity_group", sa.String(length=40), nullable=False),
        sa.Column("relevance_score", sa.Integer(), nullable=False),
        sa.Column("opportunity_score", sa.Integer(), nullable=False),
        sa.Column("recommended_action", sa.String(length=160), nullable=False),
        sa.Column("recommendation_reason", sa.String(length=500), nullable=False),
        sa.Column("tracked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "opportunity_group in ('quick_win','new_opportunity','already_found','tracked')",
            name="ck_keyword_research_suggestions_group",
        ),
        sa.CheckConstraint(
            "relevance_score between 0 and 100",
            name="ck_keyword_research_suggestions_relevance",
        ),
        sa.CheckConstraint(
            "opportunity_score between 0 and 100",
            name="ck_keyword_research_suggestions_opportunity",
        ),
        sa.ForeignKeyConstraint(["run_id"], ["keyword_research_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["business_location_id"], ["business_locations.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "normalized_keyword", name="uq_keyword_research_run_keyword"),
    )
    for column in (
        "run_id",
        "tenant_id",
        "organization_id",
        "campaign_id",
        "business_location_id",
        "opportunity_group",
        "opportunity_score",
        "created_at",
    ):
        op.create_index(
            f"ix_keyword_research_suggestions_{column}",
            "keyword_research_suggestions",
            [column],
        )
    op.create_index(
        "ix_keyword_research_suggestions_campaign_group_score",
        "keyword_research_suggestions",
        ["campaign_id", "opportunity_group", "opportunity_score"],
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
    effective_from = datetime(2026, 8, 3, tzinfo=UTC)
    op.bulk_insert(
        price_cards,
        [
            {
                "id": PRICE_CARD_IDS[0],
                "provider_name": "dataforseo",
                "capability": "keyword_research",
                "operation": "ranked_keywords_live",
                "model_name": "",
                "version": "dataforseo-keyword-research-2026-08-03-v1",
                "unit": "request",
                "unit_cost": 0.20,
                "currency": "USD",
                "effective_from": effective_from,
                "active": True,
                "source_url": "https://dataforseo.com/pricing/dataforseo-labs/labs-google",
            },
            {
                "id": PRICE_CARD_IDS[1],
                "provider_name": "dataforseo",
                "capability": "keyword_research",
                "operation": "keyword_ideas_live",
                "model_name": "",
                "version": "dataforseo-keyword-research-2026-08-03-v1",
                "unit": "request",
                "unit_cost": 0.20,
                "currency": "USD",
                "effective_from": effective_from,
                "active": True,
                "source_url": "https://dataforseo.com/pricing/dataforseo-labs/labs-google",
            },
            {
                "id": PRICE_CARD_IDS[2],
                "provider_name": "dataforseo",
                "capability": "keyword_research",
                "operation": "google_ads_search_volume_live",
                "model_name": "",
                "version": "dataforseo-keyword-research-2026-08-03-v1",
                "unit": "request",
                "unit_cost": 0.10,
                "currency": "USD",
                "effective_from": effective_from,
                "active": True,
                "source_url": "https://dataforseo.com/pricing/keywords-data/google-ads-keywords-data",
            },
        ],
    )

    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            sa.text(
                """
                GRANT SELECT, INSERT, UPDATE, DELETE
                    ON TABLE public.keyword_research_runs TO lsos_app;
                GRANT SELECT, INSERT, UPDATE, DELETE
                    ON TABLE public.keyword_research_suggestions TO lsos_app;

                ALTER TABLE public.keyword_research_runs ENABLE ROW LEVEL SECURITY;
                ALTER TABLE public.keyword_research_suggestions ENABLE ROW LEVEL SECURITY;

                CREATE POLICY lsos_tenant_isolation ON public.keyword_research_runs
                    FOR ALL TO lsos_app
                    USING (
                        current_setting('app.platform_access', true) = 'on'
                        OR (
                            tenant_id::text = current_setting('app.current_tenant_id', true)
                            AND organization_id::text = current_setting('app.current_organization_id', true)
                        )
                    )
                    WITH CHECK (
                        current_setting('app.platform_access', true) = 'on'
                        OR (
                            tenant_id::text = current_setting('app.current_tenant_id', true)
                            AND organization_id::text = current_setting('app.current_organization_id', true)
                        )
                    );

                CREATE POLICY lsos_tenant_isolation ON public.keyword_research_suggestions
                    FOR ALL TO lsos_app
                    USING (
                        current_setting('app.platform_access', true) = 'on'
                        OR (
                            tenant_id::text = current_setting('app.current_tenant_id', true)
                            AND organization_id::text = current_setting('app.current_organization_id', true)
                        )
                    )
                    WITH CHECK (
                        current_setting('app.platform_access', true) = 'on'
                        OR (
                            tenant_id::text = current_setting('app.current_tenant_id', true)
                            AND organization_id::text = current_setting('app.current_organization_id', true)
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
                DROP POLICY IF EXISTS lsos_tenant_isolation ON public.keyword_research_suggestions;
                DROP POLICY IF EXISTS lsos_tenant_isolation ON public.keyword_research_runs;
                ALTER TABLE public.keyword_research_suggestions DISABLE ROW LEVEL SECURITY;
                ALTER TABLE public.keyword_research_runs DISABLE ROW LEVEL SECURITY;
                """
            )
        )
    op.execute(
        sa.text(
            "DELETE FROM provider_price_cards WHERE id IN (:one, :two, :three)"
        ).bindparams(one=PRICE_CARD_IDS[0], two=PRICE_CARD_IDS[1], three=PRICE_CARD_IDS[2])
    )
    op.drop_index(
        "ix_keyword_research_suggestions_campaign_group_score",
        table_name="keyword_research_suggestions",
    )
    for column in reversed(
        (
            "run_id",
            "tenant_id",
            "organization_id",
            "campaign_id",
            "business_location_id",
            "opportunity_group",
            "opportunity_score",
            "created_at",
        )
    ):
        op.drop_index(
            f"ix_keyword_research_suggestions_{column}",
            table_name="keyword_research_suggestions",
        )
    op.drop_table("keyword_research_suggestions")
    op.drop_index("ix_keyword_research_runs_campaign_created", table_name="keyword_research_runs")
    for column in reversed(
        ("tenant_id", "organization_id", "campaign_id", "business_location_id", "created_at")
    ):
        op.drop_index(f"ix_keyword_research_runs_{column}", table_name="keyword_research_runs")
    op.drop_table("keyword_research_runs")

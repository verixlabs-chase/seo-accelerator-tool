"""add durable owner feedback for keyword relevance

Revision ID: 20260804_0095
Revises: 20260804_0094
Create Date: 2026-08-04 17:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260804_0095"
down_revision = "20260804_0094"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "keyword_relevance_feedback",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("campaign_id", sa.String(length=36), nullable=False),
        sa.Column("business_location_id", sa.String(length=36), nullable=True),
        sa.Column("suggestion_id", sa.String(length=36), nullable=True),
        sa.Column("service_id", sa.String(length=36), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("keyword", sa.String(length=255), nullable=False),
        sa.Column("normalized_keyword", sa.String(length=255), nullable=False),
        sa.Column("decision", sa.String(length=24), nullable=False),
        sa.Column("source", sa.String(length=24), nullable=False),
        sa.Column("rules_version", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "decision in ('relevant','unrelated','cleared')",
            name="ck_keyword_relevance_feedback_decision",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["business_location_id"], ["business_locations.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["suggestion_id"], ["keyword_research_suggestions.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["service_id"], ["business_services.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in (
        "tenant_id",
        "organization_id",
        "campaign_id",
        "business_location_id",
        "created_at",
    ):
        op.create_index(
            f"ix_keyword_relevance_feedback_{column}",
            "keyword_relevance_feedback",
            [column],
        )
    op.create_index(
        "ix_keyword_relevance_feedback_campaign_keyword_created",
        "keyword_relevance_feedback",
        ["campaign_id", "normalized_keyword", "created_at"],
    )

    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            sa.text(
                """
                GRANT SELECT, INSERT
                    ON TABLE public.keyword_relevance_feedback TO lsos_app;

                ALTER TABLE public.keyword_relevance_feedback ENABLE ROW LEVEL SECURITY;

                CREATE POLICY lsos_tenant_isolation ON public.keyword_relevance_feedback
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
                "DROP POLICY IF EXISTS lsos_tenant_isolation "
                "ON public.keyword_relevance_feedback"
            )
        )
    op.drop_index(
        "ix_keyword_relevance_feedback_campaign_keyword_created",
        table_name="keyword_relevance_feedback",
    )
    for column in reversed(
        (
            "tenant_id",
            "organization_id",
            "campaign_id",
            "business_location_id",
            "created_at",
        )
    ):
        op.drop_index(
            f"ix_keyword_relevance_feedback_{column}",
            table_name="keyword_relevance_feedback",
        )
    op.drop_table("keyword_relevance_feedback")

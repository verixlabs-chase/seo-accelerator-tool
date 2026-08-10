"""add governed reputation review inventory

Revision ID: 20260810_0108
Revises: 20260810_0107
Create Date: 2026-08-10 17:20:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260810_0108"
down_revision = "20260810_0107"
branch_labels = None
depends_on = None


def _scope_columns() -> list[sa.Column]:
    return [
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("campaign_id", sa.String(36), nullable=False),
        sa.Column("business_location_id", sa.String(36), nullable=False),
    ]


def _scope_foreign_keys(prefix: str) -> list[sa.ForeignKeyConstraint]:
    return [
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], ondelete="CASCADE", name=f"fk_{prefix}_tenant"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name=f"fk_{prefix}_organization",
        ),
        sa.ForeignKeyConstraint(
            ["campaign_id"],
            ["campaigns.id"],
            ondelete="CASCADE",
            name=f"fk_{prefix}_campaign",
        ),
        sa.ForeignKeyConstraint(
            ["business_location_id"],
            ["business_locations.id"],
            ondelete="CASCADE",
            name=f"fk_{prefix}_location",
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "reputation_reviews",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        *_scope_columns(),
        sa.Column("source_key", sa.String(100), nullable=False),
        sa.Column("source_name", sa.String(160), nullable=False),
        sa.Column("source_type", sa.String(30), nullable=False),
        sa.Column("provider_name", sa.String(100), nullable=False),
        sa.Column("external_review_id", sa.String(255), nullable=False),
        sa.Column("external_resource_name", sa.Text(), nullable=True),
        sa.Column("review_url", sa.Text(), nullable=True),
        sa.Column("rating", sa.Float(), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("author_name", sa.String(255), nullable=True),
        sa.Column("author_is_anonymous", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("response_status", sa.String(24), nullable=False, server_default="unanswered"),
        sa.Column("response_text", sa.Text(), nullable=True),
        sa.Column("response_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provider_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        *_scope_foreign_keys("reputation_reviews"),
        sa.UniqueConstraint(
            "tenant_id",
            "business_location_id",
            "source_key",
            "external_review_id",
            name="uq_reputation_reviews_location_source_external",
        ),
        sa.CheckConstraint(
            "source_type in ('owned_profile','public_competitor')",
            name="ck_reputation_reviews_source_type",
        ),
        sa.CheckConstraint(
            "response_status in ('unanswered','responded','removed','unavailable')",
            name="ck_reputation_reviews_response_status",
        ),
        sa.CheckConstraint(
            "rating >= 1 and rating <= 5",
            name="ck_reputation_reviews_rating",
        ),
    )
    op.create_table(
        "reputation_review_observations",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        *_scope_columns(),
        sa.Column("review_id", sa.String(36), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("evidence_digest", sa.String(64), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        *_scope_foreign_keys("reputation_review_obs"),
        sa.ForeignKeyConstraint(
            ["review_id"],
            ["reputation_reviews.id"],
            ondelete="CASCADE",
            name="fk_reputation_review_obs_review",
        ),
        sa.UniqueConstraint(
            "review_id",
            "evidence_digest",
            name="uq_reputation_review_obs_review_digest",
        ),
    )
    for column in (
        "tenant_id",
        "organization_id",
        "campaign_id",
        "business_location_id",
        "response_status",
        "reviewed_at",
        "last_seen_at",
    ):
        op.create_index(f"ix_reputation_reviews_{column}", "reputation_reviews", [column])
    op.create_index(
        "ix_reputation_reviews_location_response",
        "reputation_reviews",
        ["business_location_id", "response_status"],
    )
    op.create_index(
        "ix_reputation_reviews_campaign_reviewed",
        "reputation_reviews",
        ["campaign_id", "reviewed_at"],
    )
    for column in (
        "tenant_id",
        "organization_id",
        "campaign_id",
        "business_location_id",
        "review_id",
        "captured_at",
    ):
        op.create_index(
            f"ix_reputation_review_obs_{column}",
            "reputation_review_observations",
            [column],
        )
    op.create_index(
        "ix_reputation_review_obs_review_captured",
        "reputation_review_observations",
        ["review_id", "captured_at"],
    )

    if op.get_bind().dialect.name == "postgresql":
        for table in ("reputation_reviews", "reputation_review_observations"):
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
    op.drop_table("reputation_review_observations")
    op.drop_table("reputation_reviews")

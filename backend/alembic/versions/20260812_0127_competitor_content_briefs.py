"""add evidence-backed competitor content briefs

Revision ID: 20260812_0127
Revises: 20260812_0126
Create Date: 2026-08-12 22:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260812_0127"
down_revision = "20260812_0126"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "content_briefs",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("campaign_id", sa.String(36), nullable=False),
        sa.Column("business_location_id", sa.String(36), nullable=True),
        sa.Column("suggestion_id", sa.String(36), nullable=False),
        sa.Column("competitor_id", sa.String(36), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("title", sa.String(320), nullable=False),
        sa.Column("primary_keyword", sa.String(255), nullable=False),
        sa.Column("recommended_page_action", sa.String(40), nullable=False),
        sa.Column("target_url", sa.Text(), nullable=True),
        sa.Column("competitor_domain", sa.String(320), nullable=False),
        sa.Column("competitor_url", sa.Text(), nullable=True),
        sa.Column("service_name", sa.String(160), nullable=True),
        sa.Column("service_area_name", sa.String(160), nullable=True),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("outline", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["business_location_id"], ["business_locations.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["suggestion_id"], ["keyword_research_suggestions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["competitor_id"], ["competitors.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "idempotency_key", name="uq_content_briefs_tenant_idempotency"
        ),
    )
    op.create_index(
        "ix_content_briefs_campaign_created", "content_briefs", ["campaign_id", "created_at"]
    )
    for column in (
        "tenant_id",
        "organization_id",
        "campaign_id",
        "business_location_id",
        "suggestion_id",
        "competitor_id",
        "created_at",
    ):
        op.create_index(f"ix_content_briefs_{column}", "content_briefs", [column])


def downgrade() -> None:
    op.drop_table("content_briefs")

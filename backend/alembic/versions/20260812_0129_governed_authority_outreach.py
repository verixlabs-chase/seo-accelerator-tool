"""add governed manual-send authority outreach drafts

Revision ID: 20260812_0129
Revises: 20260812_0128
Create Date: 2026-08-12 23:45:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260812_0129"
down_revision = "20260812_0128"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "authority_outreach_drafts",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("campaign_id", sa.String(36), nullable=False),
        sa.Column("business_location_id", sa.String(36), nullable=True),
        sa.Column("recommendation_id", sa.String(36), nullable=True),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("source_record_id", sa.String(36), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("target_url", sa.Text(), nullable=False),
        sa.Column("referring_domain", sa.String(320), nullable=False),
        sa.Column("contact_name", sa.String(255), nullable=True),
        sa.Column("contact_email", sa.String(320), nullable=True),
        sa.Column("contact_page_url", sa.Text(), nullable=True),
        sa.Column("subject", sa.String(180), nullable=False),
        sa.Column("message_body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("owner_confirmed_recipient", sa.Boolean(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("created_by_user_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "source_type in ('competitor_gap','lost_link')",
            name="ck_authority_outreach_drafts_source_type",
        ),
        sa.CheckConstraint(
            "status in ('draft','reviewed','closed')",
            name="ck_authority_outreach_drafts_status",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["business_location_id"], ["business_locations.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["recommendation_id"], ["strategy_recommendations.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_authority_outreach_drafts_org_idempotency",
        ),
    )
    for column in (
        "tenant_id",
        "organization_id",
        "campaign_id",
        "business_location_id",
        "recommendation_id",
        "referring_domain",
        "status",
        "created_at",
    ):
        op.create_index(
            f"ix_authority_outreach_drafts_{column}",
            "authority_outreach_drafts",
            [column],
        )
    op.create_index(
        "ix_authority_outreach_drafts_campaign_created",
        "authority_outreach_drafts",
        ["campaign_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_authority_outreach_drafts_campaign_created",
        table_name="authority_outreach_drafts",
    )
    for column in reversed(
        (
            "tenant_id",
            "organization_id",
            "campaign_id",
            "business_location_id",
            "recommendation_id",
            "referring_domain",
            "status",
            "created_at",
        )
    ):
        op.drop_index(
            f"ix_authority_outreach_drafts_{column}",
            table_name="authority_outreach_drafts",
        )
    op.drop_table("authority_outreach_drafts")

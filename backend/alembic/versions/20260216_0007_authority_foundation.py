"""sprint7 authority and citation foundation tables

Revision ID: 20260216_0007
Revises: 20260216_0006
Create Date: 2026-02-16 16:55:00
"""
from alembic import op
import sqlalchemy as sa


revision = "20260216_0007"
down_revision = "20260216_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "outreach_campaigns",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("campaign_id", sa.String(length=36), sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_outreach_campaigns_tenant_id", "outreach_campaigns", ["tenant_id"])
    op.create_index("ix_outreach_campaigns_campaign_id", "outreach_campaigns", ["campaign_id"])

    op.create_table(
        "outreach_contacts",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("campaign_id", sa.String(length=36), nullable=False),
        sa.Column("outreach_campaign_id", sa.String(length=36), sa.ForeignKey("outreach_campaigns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_outreach_contacts_tenant_id", "outreach_contacts", ["tenant_id"])
    op.create_index("ix_outreach_contacts_campaign_id", "outreach_contacts", ["campaign_id"])
    op.create_index("ix_outreach_contacts_outreach_campaign_id", "outreach_contacts", ["outreach_campaign_id"])

    op.create_table(
        "backlink_opportunities",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("campaign_id", sa.String(length=36), nullable=False),
        sa.Column("domain", sa.String(length=320), nullable=False),
        sa.Column("quality_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_backlink_opportunities_tenant_id", "backlink_opportunities", ["tenant_id"])
    op.create_index("ix_backlink_opportunities_campaign_id", "backlink_opportunities", ["campaign_id"])

    op.create_table(
        "backlinks",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("campaign_id", sa.String(length=36), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("target_url", sa.Text(), nullable=False),
        sa.Column("quality_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="live"),
        sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_backlinks_tenant_id", "backlinks", ["tenant_id"])
    op.create_index("ix_backlinks_campaign_id", "backlinks", ["campaign_id"])
    op.create_index("ix_backlinks_discovered_at", "backlinks", ["discovered_at"])

    op.create_table(
        "citations",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("campaign_id", sa.String(length=36), nullable=False),
        sa.Column("directory_name", sa.String(length=255), nullable=False),
        sa.Column("submission_status", sa.String(length=40), nullable=False, server_default="submitted"),
        sa.Column("listing_url", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_citations_tenant_id", "citations", ["tenant_id"])
    op.create_index("ix_citations_campaign_id", "citations", ["campaign_id"])
    op.create_index("ix_citations_updated_at", "citations", ["updated_at"])


def downgrade() -> None:
    op.drop_index("ix_citations_updated_at", table_name="citations")
    op.drop_index("ix_citations_campaign_id", table_name="citations")
    op.drop_index("ix_citations_tenant_id", table_name="citations")
    op.drop_table("citations")

    op.drop_index("ix_backlinks_discovered_at", table_name="backlinks")
    op.drop_index("ix_backlinks_campaign_id", table_name="backlinks")
    op.drop_index("ix_backlinks_tenant_id", table_name="backlinks")
    op.drop_table("backlinks")

    op.drop_index("ix_backlink_opportunities_campaign_id", table_name="backlink_opportunities")
    op.drop_index("ix_backlink_opportunities_tenant_id", table_name="backlink_opportunities")
    op.drop_table("backlink_opportunities")

    op.drop_index("ix_outreach_contacts_outreach_campaign_id", table_name="outreach_contacts")
    op.drop_index("ix_outreach_contacts_campaign_id", table_name="outreach_contacts")
    op.drop_index("ix_outreach_contacts_tenant_id", table_name="outreach_contacts")
    op.drop_table("outreach_contacts")

    op.drop_index("ix_outreach_campaigns_campaign_id", table_name="outreach_campaigns")
    op.drop_index("ix_outreach_campaigns_tenant_id", table_name="outreach_campaigns")
    op.drop_table("outreach_campaigns")


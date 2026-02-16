"""sprint5 content foundation tables

Revision ID: 20260216_0005
Revises: 20260216_0004
Create Date: 2026-02-16 15:30:00
"""
from alembic import op
import sqlalchemy as sa


revision = "20260216_0005"
down_revision = "20260216_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "content_assets",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("campaign_id", sa.String(length=36), sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cluster_name", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=320), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("target_url", sa.Text(), nullable=True),
        sa.Column("planned_month", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_content_assets_tenant_id", "content_assets", ["tenant_id"])
    op.create_index("ix_content_assets_campaign_id", "content_assets", ["campaign_id"])

    op.create_table(
        "editorial_calendar",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("campaign_id", sa.String(length=36), nullable=False),
        sa.Column("content_asset_id", sa.String(length=36), sa.ForeignKey("content_assets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("month_number", sa.Integer(), nullable=False),
        sa.Column("planned_publish_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_editorial_calendar_tenant_id", "editorial_calendar", ["tenant_id"])
    op.create_index("ix_editorial_calendar_campaign_id", "editorial_calendar", ["campaign_id"])
    op.create_index("ix_editorial_calendar_content_asset_id", "editorial_calendar", ["content_asset_id"])

    op.create_table(
        "internal_link_map",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("campaign_id", sa.String(length=36), nullable=False),
        sa.Column("source_asset_id", sa.String(length=36), sa.ForeignKey("content_assets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_asset_id", sa.String(length=36), sa.ForeignKey("content_assets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("anchor_text", sa.String(length=255), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.75"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_internal_link_map_tenant_id", "internal_link_map", ["tenant_id"])
    op.create_index("ix_internal_link_map_campaign_id", "internal_link_map", ["campaign_id"])
    op.create_index("ix_internal_link_map_source_asset_id", "internal_link_map", ["source_asset_id"])
    op.create_index("ix_internal_link_map_target_asset_id", "internal_link_map", ["target_asset_id"])
    op.create_index("ix_internal_link_map_updated_at", "internal_link_map", ["updated_at"])

    op.create_table(
        "content_qc_events",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("campaign_id", sa.String(length=36), nullable=False),
        sa.Column("content_asset_id", sa.String(length=36), sa.ForeignKey("content_assets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("check_name", sa.String(length=120), nullable=False),
        sa.Column("passed", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("score", sa.Float(), nullable=False, server_default="1"),
        sa.Column("details_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_content_qc_events_tenant_id", "content_qc_events", ["tenant_id"])
    op.create_index("ix_content_qc_events_campaign_id", "content_qc_events", ["campaign_id"])
    op.create_index("ix_content_qc_events_content_asset_id", "content_qc_events", ["content_asset_id"])
    op.create_index("ix_content_qc_events_created_at", "content_qc_events", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_content_qc_events_created_at", table_name="content_qc_events")
    op.drop_index("ix_content_qc_events_content_asset_id", table_name="content_qc_events")
    op.drop_index("ix_content_qc_events_campaign_id", table_name="content_qc_events")
    op.drop_index("ix_content_qc_events_tenant_id", table_name="content_qc_events")
    op.drop_table("content_qc_events")

    op.drop_index("ix_internal_link_map_updated_at", table_name="internal_link_map")
    op.drop_index("ix_internal_link_map_target_asset_id", table_name="internal_link_map")
    op.drop_index("ix_internal_link_map_source_asset_id", table_name="internal_link_map")
    op.drop_index("ix_internal_link_map_campaign_id", table_name="internal_link_map")
    op.drop_index("ix_internal_link_map_tenant_id", table_name="internal_link_map")
    op.drop_table("internal_link_map")

    op.drop_index("ix_editorial_calendar_content_asset_id", table_name="editorial_calendar")
    op.drop_index("ix_editorial_calendar_campaign_id", table_name="editorial_calendar")
    op.drop_index("ix_editorial_calendar_tenant_id", table_name="editorial_calendar")
    op.drop_table("editorial_calendar")

    op.drop_index("ix_content_assets_campaign_id", table_name="content_assets")
    op.drop_index("ix_content_assets_tenant_id", table_name="content_assets")
    op.drop_table("content_assets")


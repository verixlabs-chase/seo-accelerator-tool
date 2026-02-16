"""sprint6 local foundation tables

Revision ID: 20260216_0006
Revises: 20260216_0005
Create Date: 2026-02-16 16:10:00
"""
from alembic import op
import sqlalchemy as sa


revision = "20260216_0006"
down_revision = "20260216_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "local_profiles",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("campaign_id", sa.String(length=36), sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("profile_name", sa.String(length=255), nullable=False),
        sa.Column("map_pack_position", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_local_profiles_tenant_id", "local_profiles", ["tenant_id"])
    op.create_index("ix_local_profiles_campaign_id", "local_profiles", ["campaign_id"])

    op.create_table(
        "local_health_snapshots",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("campaign_id", sa.String(length=36), nullable=False),
        sa.Column("profile_id", sa.String(length=36), sa.ForeignKey("local_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("health_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("details_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_local_health_snapshots_tenant_id", "local_health_snapshots", ["tenant_id"])
    op.create_index("ix_local_health_snapshots_campaign_id", "local_health_snapshots", ["campaign_id"])
    op.create_index("ix_local_health_snapshots_profile_id", "local_health_snapshots", ["profile_id"])
    op.create_index("ix_local_health_snapshots_captured_at", "local_health_snapshots", ["captured_at"])

    op.create_table(
        "reviews",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("campaign_id", sa.String(length=36), nullable=False),
        sa.Column("profile_id", sa.String(length=36), sa.ForeignKey("local_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("external_review_id", sa.String(length=120), nullable=False),
        sa.Column("rating", sa.Float(), nullable=False),
        sa.Column("sentiment", sa.String(length=20), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_reviews_tenant_id", "reviews", ["tenant_id"])
    op.create_index("ix_reviews_campaign_id", "reviews", ["campaign_id"])
    op.create_index("ix_reviews_profile_id", "reviews", ["profile_id"])
    op.create_index("ix_reviews_external_review_id", "reviews", ["external_review_id"])
    op.create_index("ix_reviews_reviewed_at", "reviews", ["reviewed_at"])

    op.create_table(
        "review_velocity_snapshots",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("campaign_id", sa.String(length=36), nullable=False),
        sa.Column("profile_id", sa.String(length=36), sa.ForeignKey("local_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reviews_last_30d", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("avg_rating_last_30d", sa.Float(), nullable=False, server_default="0"),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_review_velocity_snapshots_tenant_id", "review_velocity_snapshots", ["tenant_id"])
    op.create_index("ix_review_velocity_snapshots_campaign_id", "review_velocity_snapshots", ["campaign_id"])
    op.create_index("ix_review_velocity_snapshots_profile_id", "review_velocity_snapshots", ["profile_id"])
    op.create_index("ix_review_velocity_snapshots_captured_at", "review_velocity_snapshots", ["captured_at"])


def downgrade() -> None:
    op.drop_index("ix_review_velocity_snapshots_captured_at", table_name="review_velocity_snapshots")
    op.drop_index("ix_review_velocity_snapshots_profile_id", table_name="review_velocity_snapshots")
    op.drop_index("ix_review_velocity_snapshots_campaign_id", table_name="review_velocity_snapshots")
    op.drop_index("ix_review_velocity_snapshots_tenant_id", table_name="review_velocity_snapshots")
    op.drop_table("review_velocity_snapshots")

    op.drop_index("ix_reviews_reviewed_at", table_name="reviews")
    op.drop_index("ix_reviews_external_review_id", table_name="reviews")
    op.drop_index("ix_reviews_profile_id", table_name="reviews")
    op.drop_index("ix_reviews_campaign_id", table_name="reviews")
    op.drop_index("ix_reviews_tenant_id", table_name="reviews")
    op.drop_table("reviews")

    op.drop_index("ix_local_health_snapshots_captured_at", table_name="local_health_snapshots")
    op.drop_index("ix_local_health_snapshots_profile_id", table_name="local_health_snapshots")
    op.drop_index("ix_local_health_snapshots_campaign_id", table_name="local_health_snapshots")
    op.drop_index("ix_local_health_snapshots_tenant_id", table_name="local_health_snapshots")
    op.drop_table("local_health_snapshots")

    op.drop_index("ix_local_profiles_campaign_id", table_name="local_profiles")
    op.drop_index("ix_local_profiles_tenant_id", table_name="local_profiles")
    op.drop_table("local_profiles")


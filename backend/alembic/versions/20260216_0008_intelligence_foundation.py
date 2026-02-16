"""sprint8 campaign intelligence foundation tables

Revision ID: 20260216_0008
Revises: 20260216_0007
Create Date: 2026-02-16 18:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = "20260216_0008"
down_revision = "20260216_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "strategy_recommendations",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("campaign_id", sa.String(length=36), sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("recommendation_type", sa.String(length=120), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.7"),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_strategy_recommendations_tenant_id", "strategy_recommendations", ["tenant_id"])
    op.create_index("ix_strategy_recommendations_campaign_id", "strategy_recommendations", ["campaign_id"])
    op.create_index("ix_strategy_recommendations_created_at", "strategy_recommendations", ["created_at"])

    op.create_table(
        "intelligence_scores",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("campaign_id", sa.String(length=36), nullable=False),
        sa.Column("score_type", sa.String(length=80), nullable=False, server_default="composite"),
        sa.Column("score_value", sa.Float(), nullable=False, server_default="0"),
        sa.Column("details_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_intelligence_scores_tenant_id", "intelligence_scores", ["tenant_id"])
    op.create_index("ix_intelligence_scores_campaign_id", "intelligence_scores", ["campaign_id"])
    op.create_index("ix_intelligence_scores_captured_at", "intelligence_scores", ["captured_at"])

    op.create_table(
        "campaign_milestones",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("campaign_id", sa.String(length=36), sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("month_number", sa.Integer(), nullable=False),
        sa.Column("milestone_key", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="pending"),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "campaign_id", "month_number", "milestone_key", name="uq_campaign_milestone_key"),
    )
    op.create_index("ix_campaign_milestones_tenant_id", "campaign_milestones", ["tenant_id"])
    op.create_index("ix_campaign_milestones_campaign_id", "campaign_milestones", ["campaign_id"])
    op.create_index("ix_campaign_milestones_month_number", "campaign_milestones", ["month_number"])

    op.create_table(
        "anomaly_events",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("campaign_id", sa.String(length=36), nullable=False),
        sa.Column("anomaly_type", sa.String(length=120), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False, server_default="medium"),
        sa.Column("details_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_anomaly_events_tenant_id", "anomaly_events", ["tenant_id"])
    op.create_index("ix_anomaly_events_campaign_id", "anomaly_events", ["campaign_id"])
    op.create_index("ix_anomaly_events_detected_at", "anomaly_events", ["detected_at"])


def downgrade() -> None:
    op.drop_index("ix_anomaly_events_detected_at", table_name="anomaly_events")
    op.drop_index("ix_anomaly_events_campaign_id", table_name="anomaly_events")
    op.drop_index("ix_anomaly_events_tenant_id", table_name="anomaly_events")
    op.drop_table("anomaly_events")

    op.drop_index("ix_campaign_milestones_month_number", table_name="campaign_milestones")
    op.drop_index("ix_campaign_milestones_campaign_id", table_name="campaign_milestones")
    op.drop_index("ix_campaign_milestones_tenant_id", table_name="campaign_milestones")
    op.drop_table("campaign_milestones")

    op.drop_index("ix_intelligence_scores_captured_at", table_name="intelligence_scores")
    op.drop_index("ix_intelligence_scores_campaign_id", table_name="intelligence_scores")
    op.drop_index("ix_intelligence_scores_tenant_id", table_name="intelligence_scores")
    op.drop_table("intelligence_scores")

    op.drop_index("ix_strategy_recommendations_created_at", table_name="strategy_recommendations")
    op.drop_index("ix_strategy_recommendations_campaign_id", table_name="strategy_recommendations")
    op.drop_index("ix_strategy_recommendations_tenant_id", table_name="strategy_recommendations")
    op.drop_table("strategy_recommendations")


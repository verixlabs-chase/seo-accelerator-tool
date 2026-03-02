"""add campaign daily metrics

Revision ID: 20260302_0039
Revises: 20260302_0038
Create Date: 2026-03-02
"""

from __future__ import annotations

from alembic import context
from alembic import op
import sqlalchemy as sa


revision = '20260302_0039'
down_revision = '20260302_0038'
branch_labels = None
depends_on = None


def upgrade() -> None:
    offline = context.is_offline_mode()
    _ = offline

    op.create_table(
        'campaign_daily_metrics',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('portfolio_id', sa.String(length=36), nullable=True),
        sa.Column('sub_account_id', sa.String(length=36), nullable=True),
        sa.Column('campaign_id', sa.String(length=36), nullable=False),
        sa.Column('metric_date', sa.Date(), nullable=False),
        sa.Column('clicks', sa.Integer(), nullable=True),
        sa.Column('impressions', sa.Integer(), nullable=True),
        sa.Column('avg_position', sa.Float(), nullable=True),
        sa.Column('sessions', sa.Integer(), nullable=True),
        sa.Column('conversions', sa.Integer(), nullable=True),
        sa.Column('technical_issue_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('intelligence_score', sa.Float(), nullable=True),
        sa.Column('reviews_last_30d', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('avg_rating_last_30d', sa.Float(), nullable=True),
        sa.Column('cost', sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column('revenue', sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column('normalization_version', sa.String(length=32), nullable=False, server_default='analytics-v1'),
        sa.Column('deterministic_hash', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['portfolio_id'], ['portfolios.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['sub_account_id'], ['sub_accounts.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('campaign_id', 'metric_date', name='uq_campaign_daily_metrics_campaign_date'),
    )
    op.create_index('ix_campaign_daily_metrics_organization_id', 'campaign_daily_metrics', ['organization_id'])
    op.create_index('ix_campaign_daily_metrics_portfolio_id', 'campaign_daily_metrics', ['portfolio_id'])
    op.create_index('ix_campaign_daily_metrics_campaign_id', 'campaign_daily_metrics', ['campaign_id'])
    op.create_index('ix_campaign_daily_metrics_metric_date', 'campaign_daily_metrics', ['metric_date'])
    op.create_index('ix_campaign_daily_metrics_campaign_date', 'campaign_daily_metrics', ['campaign_id', 'metric_date'])


def downgrade() -> None:
    offline = context.is_offline_mode()
    _ = offline

    op.drop_index('ix_campaign_daily_metrics_campaign_date', table_name='campaign_daily_metrics')
    op.drop_index('ix_campaign_daily_metrics_metric_date', table_name='campaign_daily_metrics')
    op.drop_index('ix_campaign_daily_metrics_campaign_id', table_name='campaign_daily_metrics')
    op.drop_index('ix_campaign_daily_metrics_portfolio_id', table_name='campaign_daily_metrics')
    op.drop_index('ix_campaign_daily_metrics_organization_id', table_name='campaign_daily_metrics')
    op.drop_table('campaign_daily_metrics')

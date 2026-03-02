"""add search and analytics daily metric storage

Revision ID: 20260302_0040
Revises: 20260302_0039
Create Date: 2026-03-02
"""

from __future__ import annotations

from alembic import context
from alembic import op
import sqlalchemy as sa


revision = '20260302_0040'
down_revision = '20260302_0039'
branch_labels = None
depends_on = None


def upgrade() -> None:
    offline = context.is_offline_mode()
    _ = offline

    op.create_table(
        'search_console_daily_metrics',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('campaign_id', sa.String(length=36), nullable=False),
        sa.Column('metric_date', sa.Date(), nullable=False),
        sa.Column('clicks', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('impressions', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('avg_position', sa.Float(), nullable=True),
        sa.Column('deterministic_hash', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('campaign_id', 'metric_date', name='uq_search_console_daily_metrics_campaign_date'),
    )
    op.create_index('ix_search_console_daily_metrics_organization_id', 'search_console_daily_metrics', ['organization_id'])
    op.create_index('ix_search_console_daily_metrics_campaign_id', 'search_console_daily_metrics', ['campaign_id'])
    op.create_index('ix_search_console_daily_metrics_metric_date', 'search_console_daily_metrics', ['metric_date'])
    op.create_index('ix_search_console_daily_metrics_campaign_date', 'search_console_daily_metrics', ['campaign_id', 'metric_date'])

    op.create_table(
        'analytics_daily_metrics',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('campaign_id', sa.String(length=36), nullable=False),
        sa.Column('metric_date', sa.Date(), nullable=False),
        sa.Column('sessions', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('conversions', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('deterministic_hash', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('campaign_id', 'metric_date', name='uq_analytics_daily_metrics_campaign_date'),
    )
    op.create_index('ix_analytics_daily_metrics_organization_id', 'analytics_daily_metrics', ['organization_id'])
    op.create_index('ix_analytics_daily_metrics_campaign_id', 'analytics_daily_metrics', ['campaign_id'])
    op.create_index('ix_analytics_daily_metrics_metric_date', 'analytics_daily_metrics', ['metric_date'])
    op.create_index('ix_analytics_daily_metrics_campaign_date', 'analytics_daily_metrics', ['campaign_id', 'metric_date'])


def downgrade() -> None:
    offline = context.is_offline_mode()
    _ = offline

    op.drop_index('ix_analytics_daily_metrics_campaign_date', table_name='analytics_daily_metrics')
    op.drop_index('ix_analytics_daily_metrics_metric_date', table_name='analytics_daily_metrics')
    op.drop_index('ix_analytics_daily_metrics_campaign_id', table_name='analytics_daily_metrics')
    op.drop_index('ix_analytics_daily_metrics_organization_id', table_name='analytics_daily_metrics')
    op.drop_table('analytics_daily_metrics')

    op.drop_index('ix_search_console_daily_metrics_campaign_date', table_name='search_console_daily_metrics')
    op.drop_index('ix_search_console_daily_metrics_metric_date', table_name='search_console_daily_metrics')
    op.drop_index('ix_search_console_daily_metrics_campaign_id', table_name='search_console_daily_metrics')
    op.drop_index('ix_search_console_daily_metrics_organization_id', table_name='search_console_daily_metrics')
    op.drop_table('search_console_daily_metrics')

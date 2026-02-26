"""strategy automation events foundation

Revision ID: 20260226_0030
Revises: 20260226_0029
Create Date: 2026-02-26 22:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '20260226_0030'
down_revision = '20260226_0029'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'strategy_automation_events',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('campaign_id', sa.String(length=36), nullable=False),
        sa.Column('evaluation_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('prior_phase', sa.String(length=64), nullable=False),
        sa.Column('new_phase', sa.String(length=64), nullable=False),
        sa.Column('triggered_rules', sa.Text(), nullable=False),
        sa.Column('momentum_snapshot', sa.Text(), nullable=False),
        sa.Column('action_summary', sa.Text(), nullable=False),
        sa.Column('version_hash', sa.String(length=128), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_strategy_automation_events_campaign_id', 'strategy_automation_events', ['campaign_id'], unique=False)
    op.create_index('ix_strategy_automation_events_evaluation_date', 'strategy_automation_events', ['evaluation_date'], unique=False)
    op.create_index(
        'ix_strategy_automation_events_campaign_evaluation_date',
        'strategy_automation_events',
        ['campaign_id', 'evaluation_date'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_strategy_automation_events_campaign_evaluation_date', table_name='strategy_automation_events')
    op.drop_index('ix_strategy_automation_events_evaluation_date', table_name='strategy_automation_events')
    op.drop_index('ix_strategy_automation_events_campaign_id', table_name='strategy_automation_events')
    op.drop_table('strategy_automation_events')

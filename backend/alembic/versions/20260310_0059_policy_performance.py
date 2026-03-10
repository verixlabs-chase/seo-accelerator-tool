"""add policy performance table

Revision ID: 20260310_0059
Revises: 20260310_0058
Create Date: 2026-03-10 00:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '20260310_0059'
down_revision = '20260310_0058'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'policy_performance',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('policy_id', sa.String(length=255), nullable=False),
        sa.Column('campaign_id', sa.String(length=36), nullable=False),
        sa.Column('industry', sa.String(length=120), nullable=False, server_default='unknown'),
        sa.Column('success_score', sa.Float(), nullable=False, server_default='0'),
        sa.Column('execution_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('confidence', sa.Float(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('policy_id', 'campaign_id', 'industry', name='uq_policy_performance_scope'),
    )
    op.create_index(op.f('ix_policy_performance_policy_id'), 'policy_performance', ['policy_id'], unique=False)
    op.create_index(op.f('ix_policy_performance_campaign_id'), 'policy_performance', ['campaign_id'], unique=False)
    op.create_index(op.f('ix_policy_performance_industry'), 'policy_performance', ['industry'], unique=False)
    op.create_index('ix_policy_performance_industry_success', 'policy_performance', ['industry', 'success_score'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_policy_performance_industry_success', table_name='policy_performance')
    op.drop_index(op.f('ix_policy_performance_industry'), table_name='policy_performance')
    op.drop_index(op.f('ix_policy_performance_campaign_id'), table_name='policy_performance')
    op.drop_index(op.f('ix_policy_performance_policy_id'), table_name='policy_performance')
    op.drop_table('policy_performance')

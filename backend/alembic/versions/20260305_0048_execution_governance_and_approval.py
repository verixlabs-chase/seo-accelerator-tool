from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '20260305_0048'
down_revision = '20260305_0047'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'intelligence_governance_policies',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('campaign_id', sa.String(length=36), nullable=True),
        sa.Column('execution_type', sa.String(length=120), nullable=False),
        sa.Column('max_daily_executions', sa.Integer(), nullable=False, server_default='20'),
        sa.Column('requires_manual_approval', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('risk_level', sa.String(length=20), nullable=False, server_default='medium'),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_intelligence_governance_policies_campaign_id', 'intelligence_governance_policies', ['campaign_id'], unique=False)
    op.create_index('ix_intelligence_governance_policies_execution_type', 'intelligence_governance_policies', ['execution_type'], unique=False)

    op.add_column('recommendation_executions', sa.Column('approved_by', sa.String(length=36), nullable=True))
    op.add_column('recommendation_executions', sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('recommendation_executions', sa.Column('risk_score', sa.Float(), nullable=False, server_default='0'))
    op.add_column('recommendation_executions', sa.Column('risk_level', sa.String(length=20), nullable=False, server_default='medium'))
    op.add_column('recommendation_executions', sa.Column('scope_of_change', sa.Integer(), nullable=False, server_default='1'))
    op.add_column('recommendation_executions', sa.Column('historical_success_rate', sa.Float(), nullable=False, server_default='0'))
    op.create_index('ix_recommendation_executions_approved_by', 'recommendation_executions', ['approved_by'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_recommendation_executions_approved_by', table_name='recommendation_executions')
    op.drop_column('recommendation_executions', 'historical_success_rate')
    op.drop_column('recommendation_executions', 'scope_of_change')
    op.drop_column('recommendation_executions', 'risk_level')
    op.drop_column('recommendation_executions', 'risk_score')
    op.drop_column('recommendation_executions', 'approved_at')
    op.drop_column('recommendation_executions', 'approved_by')

    op.drop_index('ix_intelligence_governance_policies_execution_type', table_name='intelligence_governance_policies')
    op.drop_index('ix_intelligence_governance_policies_campaign_id', table_name='intelligence_governance_policies')
    op.drop_table('intelligence_governance_policies')

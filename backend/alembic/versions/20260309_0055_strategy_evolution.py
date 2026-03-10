"""strategy evolution persistence"""

from alembic import op
import sqlalchemy as sa


revision = '20260309_0055'
down_revision = '20260309_0054'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'strategy_performance',
        sa.Column('strategy_id', sa.String(length=255), primary_key=True),
        sa.Column('recommendation_type', sa.String(length=255), nullable=False),
        sa.Column('policy_id', sa.String(length=120), nullable=True),
        sa.Column('lifecycle_stage', sa.String(length=32), nullable=False, server_default='candidate'),
        sa.Column('performance_score', sa.Float(), nullable=False, server_default='0'),
        sa.Column('win_rate', sa.Float(), nullable=False, server_default='0'),
        sa.Column('avg_delta', sa.Float(), nullable=False, server_default='0'),
        sa.Column('sample_size', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('graph_score', sa.Float(), nullable=False, server_default='0'),
        sa.Column('industry_prior', sa.Float(), nullable=False, server_default='0'),
        sa.Column('promotion_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('demotion_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_outcome_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('metadata_json', sa.JSON(), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('last_updated', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_strategy_performance_recommendation_type', 'strategy_performance', ['recommendation_type'])
    op.create_index('ix_strategy_performance_policy_id', 'strategy_performance', ['policy_id'])
    op.create_index('ix_strategy_performance_lifecycle_stage', 'strategy_performance', ['lifecycle_stage'])

    op.create_table(
        'strategy_experiments',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('strategy_id', sa.String(length=255), nullable=False),
        sa.Column('variant_strategy_id', sa.String(length=255), nullable=False),
        sa.Column('campaign_id', sa.String(length=36), sa.ForeignKey('campaigns.id', ondelete='SET NULL'), nullable=True),
        sa.Column('hypothesis', sa.Text(), nullable=False),
        sa.Column('mutation_payload', sa.JSON(), nullable=False),
        sa.Column('predicted_rank_delta', sa.Float(), nullable=False, server_default='0'),
        sa.Column('predicted_traffic_delta', sa.Float(), nullable=False, server_default='0'),
        sa.Column('confidence', sa.Float(), nullable=False, server_default='0'),
        sa.Column('expected_value', sa.Float(), nullable=False, server_default='0'),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='proposed'),
        sa.Column('result_delta', sa.Float(), nullable=True),
        sa.Column('metadata_json', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_strategy_experiments_strategy_id', 'strategy_experiments', ['strategy_id'])
    op.create_index('ix_strategy_experiments_variant_strategy_id', 'strategy_experiments', ['variant_strategy_id'])
    op.create_index('ix_strategy_experiments_campaign_id', 'strategy_experiments', ['campaign_id'])
    op.create_index('ix_strategy_experiments_status', 'strategy_experiments', ['status'])


def downgrade() -> None:
    op.drop_index('ix_strategy_experiments_status', table_name='strategy_experiments')
    op.drop_index('ix_strategy_experiments_campaign_id', table_name='strategy_experiments')
    op.drop_index('ix_strategy_experiments_variant_strategy_id', table_name='strategy_experiments')
    op.drop_index('ix_strategy_experiments_strategy_id', table_name='strategy_experiments')
    op.drop_table('strategy_experiments')

    op.drop_index('ix_strategy_performance_lifecycle_stage', table_name='strategy_performance')
    op.drop_index('ix_strategy_performance_policy_id', table_name='strategy_performance')
    op.drop_index('ix_strategy_performance_recommendation_type', table_name='strategy_performance')
    op.drop_table('strategy_performance')

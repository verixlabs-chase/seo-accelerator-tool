"""network learning persistence"""

from alembic import op
import sqlalchemy as sa


revision = '20260309_0056'
down_revision = '20260309_0055'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'seo_mutation_outcomes',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('execution_id', sa.String(length=36), sa.ForeignKey('recommendation_executions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('mutation_id', sa.String(length=36), sa.ForeignKey('execution_mutations.id', ondelete='SET NULL'), nullable=True),
        sa.Column('campaign_id', sa.String(length=36), nullable=False),
        sa.Column('industry_id', sa.String(length=120), nullable=False, server_default='unknown'),
        sa.Column('mutation_type', sa.String(length=80), nullable=False),
        sa.Column('page_url', sa.String(length=500), nullable=False),
        sa.Column('rank_before', sa.Float(), nullable=False, server_default='0'),
        sa.Column('rank_after', sa.Float(), nullable=False, server_default='0'),
        sa.Column('traffic_before', sa.Float(), nullable=False, server_default='0'),
        sa.Column('traffic_after', sa.Float(), nullable=False, server_default='0'),
        sa.Column('measured_delta', sa.Float(), nullable=False, server_default='0'),
        sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_seo_mutation_outcomes_execution_id', 'seo_mutation_outcomes', ['execution_id'])
    op.create_index('ix_seo_mutation_outcomes_mutation_id', 'seo_mutation_outcomes', ['mutation_id'])
    op.create_index('ix_seo_mutation_outcomes_campaign_id', 'seo_mutation_outcomes', ['campaign_id'])
    op.create_index('ix_seo_mutation_outcomes_industry_id', 'seo_mutation_outcomes', ['industry_id'])
    op.create_index('ix_seo_mutation_outcomes_mutation_type', 'seo_mutation_outcomes', ['mutation_type'])

    op.create_table(
        'seo_experiment_results',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('experiment_id', sa.String(length=36), nullable=False),
        sa.Column('strategy_id', sa.String(length=255), nullable=False),
        sa.Column('variant_strategy_id', sa.String(length=255), nullable=False),
        sa.Column('industry_id', sa.String(length=120), nullable=False, server_default='unknown'),
        sa.Column('campaign_id', sa.String(length=36), nullable=True),
        sa.Column('hypothesis', sa.Text(), nullable=False),
        sa.Column('predicted_effect', sa.Float(), nullable=False, server_default='0'),
        sa.Column('actual_effect', sa.Float(), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=False, server_default='0'),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='proposed'),
        sa.Column('metadata_json', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_seo_experiment_results_experiment_id', 'seo_experiment_results', ['experiment_id'])
    op.create_index('ix_seo_experiment_results_strategy_id', 'seo_experiment_results', ['strategy_id'])
    op.create_index('ix_seo_experiment_results_variant_strategy_id', 'seo_experiment_results', ['variant_strategy_id'])
    op.create_index('ix_seo_experiment_results_industry_id', 'seo_experiment_results', ['industry_id'])
    op.create_index('ix_seo_experiment_results_campaign_id', 'seo_experiment_results', ['campaign_id'])
    op.create_index('ix_seo_experiment_results_status', 'seo_experiment_results', ['status'])

    op.create_table(
        'industry_similarity_matrix',
        sa.Column('similarity_key', sa.String(length=255), primary_key=True),
        sa.Column('source_industry_id', sa.String(length=120), nullable=False),
        sa.Column('target_industry_id', sa.String(length=120), nullable=False),
        sa.Column('similarity_score', sa.Float(), nullable=False, server_default='0'),
        sa.Column('transfer_allowed', sa.Float(), nullable=False, server_default='0'),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_industry_similarity_matrix_source_industry_id', 'industry_similarity_matrix', ['source_industry_id'])
    op.create_index('ix_industry_similarity_matrix_target_industry_id', 'industry_similarity_matrix', ['target_industry_id'])


def downgrade() -> None:
    op.drop_index('ix_industry_similarity_matrix_target_industry_id', table_name='industry_similarity_matrix')
    op.drop_index('ix_industry_similarity_matrix_source_industry_id', table_name='industry_similarity_matrix')
    op.drop_table('industry_similarity_matrix')

    op.drop_index('ix_seo_experiment_results_status', table_name='seo_experiment_results')
    op.drop_index('ix_seo_experiment_results_campaign_id', table_name='seo_experiment_results')
    op.drop_index('ix_seo_experiment_results_industry_id', table_name='seo_experiment_results')
    op.drop_index('ix_seo_experiment_results_variant_strategy_id', table_name='seo_experiment_results')
    op.drop_index('ix_seo_experiment_results_strategy_id', table_name='seo_experiment_results')
    op.drop_index('ix_seo_experiment_results_experiment_id', table_name='seo_experiment_results')
    op.drop_table('seo_experiment_results')

    op.drop_index('ix_seo_mutation_outcomes_mutation_type', table_name='seo_mutation_outcomes')
    op.drop_index('ix_seo_mutation_outcomes_industry_id', table_name='seo_mutation_outcomes')
    op.drop_index('ix_seo_mutation_outcomes_campaign_id', table_name='seo_mutation_outcomes')
    op.drop_index('ix_seo_mutation_outcomes_mutation_id', table_name='seo_mutation_outcomes')
    op.drop_index('ix_seo_mutation_outcomes_execution_id', table_name='seo_mutation_outcomes')
    op.drop_table('seo_mutation_outcomes')

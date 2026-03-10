"""add experiment network persistence

Revision ID: 20260310_0060
Revises: 20260310_0059
Create Date: 2026-03-10 01:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '20260310_0060'
down_revision = '20260310_0059'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'experiments',
        sa.Column('experiment_id', sa.String(length=36), nullable=False),
        sa.Column('policy_id', sa.String(length=255), nullable=False),
        sa.Column('hypothesis', sa.String(length=500), nullable=False),
        sa.Column('experiment_type', sa.String(length=80), nullable=False, server_default='portfolio_policy'),
        sa.Column('cohort_size', sa.Integer(), nullable=False, server_default='100'),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='active'),
        sa.Column('industry', sa.String(length=120), nullable=False, server_default='unknown'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('experiment_id'),
    )
    op.create_index(op.f('ix_experiments_policy_id'), 'experiments', ['policy_id'], unique=False)
    op.create_index(op.f('ix_experiments_status'), 'experiments', ['status'], unique=False)
    op.create_index(op.f('ix_experiments_industry'), 'experiments', ['industry'], unique=False)

    op.create_table(
        'experiment_assignments',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('experiment_id', sa.String(length=36), nullable=False),
        sa.Column('campaign_id', sa.String(length=36), nullable=False),
        sa.Column('cohort', sa.String(length=16), nullable=False),
        sa.Column('bucket', sa.Integer(), nullable=False),
        sa.Column('assigned_policy_id', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['experiment_id'], ['experiments.experiment_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('experiment_id', 'campaign_id', name='uq_experiment_assignment_campaign'),
    )
    op.create_index(op.f('ix_experiment_assignments_experiment_id'), 'experiment_assignments', ['experiment_id'], unique=False)
    op.create_index(op.f('ix_experiment_assignments_campaign_id'), 'experiment_assignments', ['campaign_id'], unique=False)
    op.create_index(op.f('ix_experiment_assignments_cohort'), 'experiment_assignments', ['cohort'], unique=False)

    op.create_table(
        'experiment_outcomes',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('experiment_id', sa.String(length=36), nullable=False),
        sa.Column('assignment_id', sa.String(length=36), nullable=False),
        sa.Column('outcome_id', sa.String(length=36), nullable=False),
        sa.Column('campaign_id', sa.String(length=36), nullable=False),
        sa.Column('metric_before', sa.Float(), nullable=False, server_default='0'),
        sa.Column('metric_after', sa.Float(), nullable=False, server_default='0'),
        sa.Column('delta', sa.Float(), nullable=False, server_default='0'),
        sa.Column('success_flag', sa.Float(), nullable=False, server_default='0'),
        sa.Column('measured_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['assignment_id'], ['experiment_assignments.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['experiment_id'], ['experiments.experiment_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['outcome_id'], ['recommendation_outcomes.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('outcome_id', name='uq_experiment_outcome_source'),
    )
    op.create_index(op.f('ix_experiment_outcomes_experiment_id'), 'experiment_outcomes', ['experiment_id'], unique=False)
    op.create_index(op.f('ix_experiment_outcomes_assignment_id'), 'experiment_outcomes', ['assignment_id'], unique=False)
    op.create_index(op.f('ix_experiment_outcomes_outcome_id'), 'experiment_outcomes', ['outcome_id'], unique=False)
    op.create_index(op.f('ix_experiment_outcomes_campaign_id'), 'experiment_outcomes', ['campaign_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_experiment_outcomes_campaign_id'), table_name='experiment_outcomes')
    op.drop_index(op.f('ix_experiment_outcomes_outcome_id'), table_name='experiment_outcomes')
    op.drop_index(op.f('ix_experiment_outcomes_assignment_id'), table_name='experiment_outcomes')
    op.drop_index(op.f('ix_experiment_outcomes_experiment_id'), table_name='experiment_outcomes')
    op.drop_table('experiment_outcomes')
    op.drop_index(op.f('ix_experiment_assignments_cohort'), table_name='experiment_assignments')
    op.drop_index(op.f('ix_experiment_assignments_campaign_id'), table_name='experiment_assignments')
    op.drop_index(op.f('ix_experiment_assignments_experiment_id'), table_name='experiment_assignments')
    op.drop_table('experiment_assignments')
    op.drop_index(op.f('ix_experiments_industry'), table_name='experiments')
    op.drop_index(op.f('ix_experiments_status'), table_name='experiments')
    op.drop_index(op.f('ix_experiments_policy_id'), table_name='experiments')
    op.drop_table('experiments')

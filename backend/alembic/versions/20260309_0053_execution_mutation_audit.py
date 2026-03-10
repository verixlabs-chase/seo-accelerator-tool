"""execution mutation audit trail and rollback state

Revision ID: 20260309_0053
Revises: 20260309_0052
Create Date: 2026-03-09 00:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '20260309_0053'
down_revision = '20260309_0052'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('recommendation_executions', sa.Column('rolled_back_at', sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        'execution_mutations',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('execution_id', sa.String(length=36), nullable=False),
        sa.Column('recommendation_id', sa.String(length=36), nullable=False),
        sa.Column('campaign_id', sa.String(length=36), nullable=False),
        sa.Column('provider_name', sa.String(length=80), nullable=False),
        sa.Column('mutation_type', sa.String(length=80), nullable=False),
        sa.Column('target_url', sa.String(length=500), nullable=False),
        sa.Column('external_mutation_id', sa.String(length=120), nullable=True),
        sa.Column('mutation_payload', sa.Text(), nullable=False),
        sa.Column('before_state', sa.Text(), nullable=True),
        sa.Column('after_state', sa.Text(), nullable=True),
        sa.Column('rollback_payload', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=30), nullable=False),
        sa.Column('applied_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('rolled_back_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['execution_id'], ['recommendation_executions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_execution_mutations_execution_id', 'execution_mutations', ['execution_id'])
    op.create_index('ix_execution_mutations_recommendation_id', 'execution_mutations', ['recommendation_id'])
    op.create_index('ix_execution_mutations_campaign_id', 'execution_mutations', ['campaign_id'])
    op.create_index('ix_execution_mutations_provider_name', 'execution_mutations', ['provider_name'])
    op.create_index('ix_execution_mutations_mutation_type', 'execution_mutations', ['mutation_type'])
    op.create_index('ix_execution_mutations_status', 'execution_mutations', ['status'])
    op.create_index('ix_execution_mutations_created_at', 'execution_mutations', ['created_at'])
    op.create_index('ix_execution_mutations_external_mutation_id', 'execution_mutations', ['external_mutation_id'])


def downgrade() -> None:
    op.drop_index('ix_execution_mutations_external_mutation_id', table_name='execution_mutations')
    op.drop_index('ix_execution_mutations_created_at', table_name='execution_mutations')
    op.drop_index('ix_execution_mutations_status', table_name='execution_mutations')
    op.drop_index('ix_execution_mutations_mutation_type', table_name='execution_mutations')
    op.drop_index('ix_execution_mutations_provider_name', table_name='execution_mutations')
    op.drop_index('ix_execution_mutations_campaign_id', table_name='execution_mutations')
    op.drop_index('ix_execution_mutations_recommendation_id', table_name='execution_mutations')
    op.drop_index('ix_execution_mutations_execution_id', table_name='execution_mutations')
    op.drop_table('execution_mutations')
    op.drop_column('recommendation_executions', 'rolled_back_at')

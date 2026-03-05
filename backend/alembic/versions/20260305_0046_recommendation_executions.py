from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = '20260305_0046'
down_revision = '20260305_0045'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'recommendation_executions',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('recommendation_id', sa.String(length=36), nullable=False),
        sa.Column('campaign_id', sa.String(length=36), nullable=False),
        sa.Column('execution_type', sa.String(length=120), nullable=False),
        sa.Column('execution_payload', sa.Text(), nullable=False, server_default='{}'),
        sa.Column('idempotency_key', sa.String(length=160), nullable=False),
        sa.Column('deterministic_hash', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=30), nullable=False, server_default='pending'),
        sa.Column('attempt_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('result_summary', sa.Text(), nullable=True),
        sa.Column('executed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['recommendation_id'], ['strategy_recommendations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('idempotency_key', name='uq_recommendation_executions_idempotency_key'),
    )
    op.create_index('ix_recommendation_executions_recommendation_id', 'recommendation_executions', ['recommendation_id'], unique=False)
    op.create_index('ix_recommendation_executions_campaign_id', 'recommendation_executions', ['campaign_id'], unique=False)
    op.create_index('ix_recommendation_executions_execution_type', 'recommendation_executions', ['execution_type'], unique=False)
    op.create_index('ix_recommendation_executions_status', 'recommendation_executions', ['status'], unique=False)
    op.create_index('ix_recommendation_executions_created_at', 'recommendation_executions', ['created_at'], unique=False)
    op.create_index('ix_recommendation_executions_deterministic_hash', 'recommendation_executions', ['deterministic_hash'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_recommendation_executions_deterministic_hash', table_name='recommendation_executions')
    op.drop_index('ix_recommendation_executions_created_at', table_name='recommendation_executions')
    op.drop_index('ix_recommendation_executions_status', table_name='recommendation_executions')
    op.drop_index('ix_recommendation_executions_execution_type', table_name='recommendation_executions')
    op.drop_index('ix_recommendation_executions_campaign_id', table_name='recommendation_executions')
    op.drop_index('ix_recommendation_executions_recommendation_id', table_name='recommendation_executions')
    op.drop_table('recommendation_executions')

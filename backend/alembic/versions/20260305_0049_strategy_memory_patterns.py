from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '20260305_0049'
down_revision = '20260305_0048'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'strategy_memory_patterns',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('pattern_name', sa.String(length=180), nullable=False),
        sa.Column('feature_name', sa.String(length=120), nullable=False),
        sa.Column('pattern_description', sa.String(length=500), nullable=False),
        sa.Column('support_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('avg_outcome_delta', sa.Float(), nullable=False, server_default='0'),
        sa.Column('confidence_score', sa.Float(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_strategy_memory_patterns_pattern_name', 'strategy_memory_patterns', ['pattern_name'], unique=False)
    op.create_index('ix_strategy_memory_patterns_feature_name', 'strategy_memory_patterns', ['feature_name'], unique=False)
    op.create_index('ix_strategy_memory_patterns_created_at', 'strategy_memory_patterns', ['created_at'], unique=False)
    op.create_index('ix_strategy_memory_patterns_updated_at', 'strategy_memory_patterns', ['updated_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_strategy_memory_patterns_updated_at', table_name='strategy_memory_patterns')
    op.drop_index('ix_strategy_memory_patterns_created_at', table_name='strategy_memory_patterns')
    op.drop_index('ix_strategy_memory_patterns_feature_name', table_name='strategy_memory_patterns')
    op.drop_index('ix_strategy_memory_patterns_pattern_name', table_name='strategy_memory_patterns')
    op.drop_table('strategy_memory_patterns')

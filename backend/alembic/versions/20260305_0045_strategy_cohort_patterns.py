from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = '20260305_0045'
down_revision = '20260305_0044'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'strategy_cohort_patterns',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('pattern_name', sa.String(length=160), nullable=False),
        sa.Column('feature_name', sa.String(length=120), nullable=False),
        sa.Column('cohort_definition', sa.String(length=255), nullable=False),
        sa.Column('pattern_strength', sa.Float(), nullable=False, server_default='0'),
        sa.Column('support_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('confidence', sa.Float(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_strategy_cohort_patterns_pattern_name', 'strategy_cohort_patterns', ['pattern_name'], unique=False)
    op.create_index('ix_strategy_cohort_patterns_feature_name', 'strategy_cohort_patterns', ['feature_name'], unique=False)
    op.create_index('ix_strategy_cohort_patterns_cohort_definition', 'strategy_cohort_patterns', ['cohort_definition'], unique=False)
    op.create_index('ix_strategy_cohort_patterns_created_at', 'strategy_cohort_patterns', ['created_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_strategy_cohort_patterns_created_at', table_name='strategy_cohort_patterns')
    op.drop_index('ix_strategy_cohort_patterns_cohort_definition', table_name='strategy_cohort_patterns')
    op.drop_index('ix_strategy_cohort_patterns_feature_name', table_name='strategy_cohort_patterns')
    op.drop_index('ix_strategy_cohort_patterns_pattern_name', table_name='strategy_cohort_patterns')
    op.drop_table('strategy_cohort_patterns')

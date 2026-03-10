"""add strategy evolution log

Revision ID: 20260310_0062
Revises: 20260310_0061
Create Date: 2026-03-10 01:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '20260310_0062'
down_revision = '20260310_0061'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'strategy_evolution_logs',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('parent_policy', sa.String(length=255), nullable=False),
        sa.Column('new_policy', sa.String(length=255), nullable=False),
        sa.Column('mutation_type', sa.String(length=120), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('parent_policy', 'new_policy', name='uq_strategy_evolution_log_policy_pair'),
    )
    op.create_index(op.f('ix_strategy_evolution_logs_parent_policy'), 'strategy_evolution_logs', ['parent_policy'], unique=False)
    op.create_index(op.f('ix_strategy_evolution_logs_new_policy'), 'strategy_evolution_logs', ['new_policy'], unique=False)
    op.create_index('ix_strategy_evolution_logs_parent_created', 'strategy_evolution_logs', ['parent_policy', 'created_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_strategy_evolution_logs_parent_created', table_name='strategy_evolution_logs')
    op.drop_index(op.f('ix_strategy_evolution_logs_new_policy'), table_name='strategy_evolution_logs')
    op.drop_index(op.f('ix_strategy_evolution_logs_parent_policy'), table_name='strategy_evolution_logs')
    op.drop_table('strategy_evolution_logs')

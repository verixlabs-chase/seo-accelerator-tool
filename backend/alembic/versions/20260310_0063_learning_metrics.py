"""add learning metrics telemetry

Revision ID: 20260310_0063
Revises: 20260310_0062
Create Date: 2026-03-10 02:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '20260310_0063'
down_revision = '20260310_0062'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'learning_metrics',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('mutation_success_rate', sa.Float(), nullable=False, server_default='0'),
        sa.Column('experiment_win_rate', sa.Float(), nullable=False, server_default='0'),
        sa.Column('causal_confidence_mean', sa.Float(), nullable=False, server_default='0'),
        sa.Column('policy_improvement_velocity', sa.Float(), nullable=False, server_default='0'),
        sa.Column('mutation_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('experiment_count', sa.Integer(), nullable=False, server_default='0'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_learning_metrics_timestamp'), 'learning_metrics', ['timestamp'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_learning_metrics_timestamp'), table_name='learning_metrics')
    op.drop_table('learning_metrics')

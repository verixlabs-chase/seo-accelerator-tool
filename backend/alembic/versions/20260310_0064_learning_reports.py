"""add learning reports

Revision ID: 20260310_0064
Revises: 20260310_0063
Create Date: 2026-03-10 02:15:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '20260310_0064'
down_revision = '20260310_0063'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'learning_reports',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('report_date', sa.Date(), nullable=False),
        sa.Column('mutation_success_rate', sa.Float(), nullable=False, server_default='0'),
        sa.Column('experiment_win_rate', sa.Float(), nullable=False, server_default='0'),
        sa.Column('policy_improvement_velocity', sa.Float(), nullable=False, server_default='0'),
        sa.Column('causal_confidence_mean', sa.Float(), nullable=False, server_default='0'),
        sa.Column('trend', sa.String(length=32), nullable=False, server_default='stable'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_learning_reports_report_date'), 'learning_reports', ['report_date'], unique=False)
    op.create_index(op.f('ix_learning_reports_created_at'), 'learning_reports', ['created_at'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_learning_reports_created_at'), table_name='learning_reports')
    op.drop_index(op.f('ix_learning_reports_report_date'), table_name='learning_reports')
    op.drop_table('learning_reports')

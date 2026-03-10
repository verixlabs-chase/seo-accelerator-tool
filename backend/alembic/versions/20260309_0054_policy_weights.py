"""policy weight persistence

Revision ID: 20260309_0054
Revises: 20260309_0053
Create Date: 2026-03-09 01:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '20260309_0054'
down_revision = '20260309_0053'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'policy_weights',
        sa.Column('policy_id', sa.String(length=255), nullable=False),
        sa.Column('weight', sa.Float(), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('sample_size', sa.Integer(), nullable=False),
        sa.Column('last_updated', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('policy_id'),
    )


def downgrade() -> None:
    op.drop_table('policy_weights')

"""expand strategy recommendation type to text

Revision ID: 20260310_0058
Revises: 20260309_0057
Create Date: 2026-03-10 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '20260310_0058'
down_revision = '20260309_0057'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('strategy_recommendations') as batch_op:
        batch_op.alter_column(
            'recommendation_type',
            existing_type=sa.String(length=120),
            type_=sa.Text(),
            existing_nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table('strategy_recommendations') as batch_op:
        batch_op.alter_column(
            'recommendation_type',
            existing_type=sa.Text(),
            type_=sa.String(length=120),
            existing_nullable=False,
        )

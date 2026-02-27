"""add trace payload to strategy automation events

Revision ID: 20260227_0032
Revises: 20260227_0031
Create Date: 2026-02-27 00:45:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '20260227_0032'
down_revision = '20260227_0031'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('strategy_automation_events', sa.Column('trace_payload', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('strategy_automation_events', 'trace_payload')
"""add decision hash to strategy automation events

Revision ID: 20260227_0031
Revises: 20260226_0030
Create Date: 2026-02-27 00:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '20260227_0031'
down_revision = '20260226_0030'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('strategy_automation_events', sa.Column('decision_hash', sa.String(length=64), nullable=True))
    op.create_index('ix_strategy_automation_events_decision_hash', 'strategy_automation_events', ['decision_hash'], unique=False)
    op.execute("UPDATE strategy_automation_events SET decision_hash = NULL WHERE decision_hash IS NULL")


def downgrade() -> None:
    op.drop_index('ix_strategy_automation_events_decision_hash', table_name='strategy_automation_events')
    op.drop_column('strategy_automation_events', 'decision_hash')

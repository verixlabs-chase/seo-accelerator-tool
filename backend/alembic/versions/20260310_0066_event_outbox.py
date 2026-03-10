"""add event outbox persistence

Revision ID: 20260310_0066
Revises: 20260310_0065
Create Date: 2026-03-10 07:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '20260310_0066'
down_revision = '20260310_0065'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'event_outbox',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('event_type', sa.String(length=120), nullable=False),
        sa.Column('payload_json', sa.Text(), nullable=False),
        sa.Column('payload_hash', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=24), nullable=False, server_default='pending'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('event_type', 'payload_hash', name='uq_event_outbox_event_type_payload_hash'),
    )
    op.create_index(op.f('ix_event_outbox_event_type'), 'event_outbox', ['event_type'], unique=False)
    op.create_index(op.f('ix_event_outbox_payload_hash'), 'event_outbox', ['payload_hash'], unique=False)
    op.create_index(op.f('ix_event_outbox_status'), 'event_outbox', ['status'], unique=False)
    op.create_index(op.f('ix_event_outbox_created_at'), 'event_outbox', ['created_at'], unique=False)
    op.create_index(op.f('ix_event_outbox_processed_at'), 'event_outbox', ['processed_at'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_event_outbox_processed_at'), table_name='event_outbox')
    op.drop_index(op.f('ix_event_outbox_created_at'), table_name='event_outbox')
    op.drop_index(op.f('ix_event_outbox_status'), table_name='event_outbox')
    op.drop_index(op.f('ix_event_outbox_payload_hash'), table_name='event_outbox')
    op.drop_index(op.f('ix_event_outbox_event_type'), table_name='event_outbox')
    op.drop_table('event_outbox')

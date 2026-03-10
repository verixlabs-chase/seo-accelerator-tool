"""add causal learning graph persistence

Revision ID: 20260310_0061
Revises: 20260310_0060
Create Date: 2026-03-10 01:15:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '20260310_0061'
down_revision = '20260310_0060'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'causal_edges',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('source_node', sa.String(length=255), nullable=False),
        sa.Column('target_node', sa.String(length=255), nullable=False),
        sa.Column('policy_id', sa.String(length=255), nullable=False),
        sa.Column('effect_size', sa.Float(), nullable=False, server_default='0'),
        sa.Column('confidence', sa.Float(), nullable=False, server_default='0'),
        sa.Column('sample_size', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('industry', sa.String(length=120), nullable=False, server_default='unknown'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('source_node', 'target_node', 'policy_id', 'industry', name='uq_causal_edge_identity'),
    )
    op.create_index(op.f('ix_causal_edges_source_node'), 'causal_edges', ['source_node'], unique=False)
    op.create_index(op.f('ix_causal_edges_policy_id'), 'causal_edges', ['policy_id'], unique=False)
    op.create_index(op.f('ix_causal_edges_industry'), 'causal_edges', ['industry'], unique=False)
    op.create_index('ix_causal_edges_industry_confidence', 'causal_edges', ['industry', 'confidence'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_causal_edges_industry_confidence', table_name='causal_edges')
    op.drop_index(op.f('ix_causal_edges_industry'), table_name='causal_edges')
    op.drop_index(op.f('ix_causal_edges_policy_id'), table_name='causal_edges')
    op.drop_index(op.f('ix_causal_edges_source_node'), table_name='causal_edges')
    op.drop_table('causal_edges')

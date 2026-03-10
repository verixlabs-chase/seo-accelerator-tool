"""add global knowledge graph persistence

Revision ID: 20260310_0067
Revises: 20260310_0066
Create Date: 2026-03-10 08:10:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '20260310_0067'
down_revision = '20260310_0066'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'knowledge_nodes',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('node_type', sa.String(length=32), nullable=False),
        sa.Column('node_key', sa.String(length=255), nullable=False),
        sa.Column('label', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('node_type', 'node_key', name='uq_knowledge_nodes_type_key'),
    )
    op.create_index(op.f('ix_knowledge_nodes_node_type'), 'knowledge_nodes', ['node_type'], unique=False)
    op.create_index(op.f('ix_knowledge_nodes_node_key'), 'knowledge_nodes', ['node_key'], unique=False)
    op.create_index(op.f('ix_knowledge_nodes_created_at'), 'knowledge_nodes', ['created_at'], unique=False)

    op.create_table(
        'knowledge_edges',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('source_node_id', sa.String(length=36), nullable=False),
        sa.Column('target_node_id', sa.String(length=36), nullable=False),
        sa.Column('edge_type', sa.String(length=64), nullable=False),
        sa.Column('industry', sa.String(length=120), nullable=False, server_default='unknown'),
        sa.Column('effect_size', sa.Float(), nullable=False, server_default='0'),
        sa.Column('confidence', sa.Float(), nullable=False, server_default='0'),
        sa.Column('sample_size', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['source_node_id'], ['knowledge_nodes.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['target_node_id'], ['knowledge_nodes.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('source_node_id', 'target_node_id', 'edge_type', 'industry', name='uq_knowledge_edges_identity'),
    )
    op.create_index(op.f('ix_knowledge_edges_source_node_id'), 'knowledge_edges', ['source_node_id'], unique=False)
    op.create_index(op.f('ix_knowledge_edges_target_node_id'), 'knowledge_edges', ['target_node_id'], unique=False)
    op.create_index(op.f('ix_knowledge_edges_edge_type'), 'knowledge_edges', ['edge_type'], unique=False)
    op.create_index(op.f('ix_knowledge_edges_industry'), 'knowledge_edges', ['industry'], unique=False)
    op.create_index(op.f('ix_knowledge_edges_updated_at'), 'knowledge_edges', ['updated_at'], unique=False)
    op.create_index('ix_knowledge_edges_industry_confidence', 'knowledge_edges', ['industry', 'confidence'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_knowledge_edges_industry_confidence', table_name='knowledge_edges')
    op.drop_index(op.f('ix_knowledge_edges_updated_at'), table_name='knowledge_edges')
    op.drop_index(op.f('ix_knowledge_edges_industry'), table_name='knowledge_edges')
    op.drop_index(op.f('ix_knowledge_edges_edge_type'), table_name='knowledge_edges')
    op.drop_index(op.f('ix_knowledge_edges_target_node_id'), table_name='knowledge_edges')
    op.drop_index(op.f('ix_knowledge_edges_source_node_id'), table_name='knowledge_edges')
    op.drop_table('knowledge_edges')

    op.drop_index(op.f('ix_knowledge_nodes_created_at'), table_name='knowledge_nodes')
    op.drop_index(op.f('ix_knowledge_nodes_node_key'), table_name='knowledge_nodes')
    op.drop_index(op.f('ix_knowledge_nodes_node_type'), table_name='knowledge_nodes')
    op.drop_table('knowledge_nodes')

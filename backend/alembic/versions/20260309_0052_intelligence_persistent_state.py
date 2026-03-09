"""persistent intelligence state foundation

Revision ID: 20260309_0052
Revises: 20260305_0051
Create Date: 2026-03-09 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '20260309_0052'
down_revision = '20260305_0051'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'industry_intelligence_models',
        sa.Column('industry_id', sa.String(length=120), nullable=False),
        sa.Column('industry_name', sa.String(length=255), nullable=False),
        sa.Column('pattern_distribution', sa.JSON(), nullable=False),
        sa.Column('strategy_success_rates', sa.JSON(), nullable=False),
        sa.Column('avg_rank_delta', sa.Float(), nullable=False),
        sa.Column('avg_traffic_delta', sa.Float(), nullable=False),
        sa.Column('confidence_score', sa.Float(), nullable=False),
        sa.Column('sample_size', sa.Integer(), nullable=False),
        sa.Column('support_state', sa.JSON(), nullable=False),
        sa.Column('last_updated', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('industry_id'),
    )

    op.create_table(
        'intelligence_graph_nodes',
        sa.Column('node_id', sa.String(length=255), nullable=False),
        sa.Column('node_type', sa.String(length=40), nullable=False),
        sa.Column('metadata_json', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('node_id'),
    )
    op.create_index('ix_intelligence_graph_nodes_node_type', 'intelligence_graph_nodes', ['node_type'])
    op.create_index('ix_intelligence_graph_nodes_updated_at', 'intelligence_graph_nodes', ['updated_at'])

    op.create_table(
        'intelligence_graph_edges',
        sa.Column('edge_id', sa.String(length=64), nullable=False),
        sa.Column('source_id', sa.String(length=255), nullable=False),
        sa.Column('target_id', sa.String(length=255), nullable=False),
        sa.Column('edge_type', sa.String(length=40), nullable=False),
        sa.Column('metadata_json', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['source_id'], ['intelligence_graph_nodes.node_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['target_id'], ['intelligence_graph_nodes.node_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('edge_id'),
    )
    op.create_index('ix_intelligence_graph_edges_source_id', 'intelligence_graph_edges', ['source_id'])
    op.create_index('ix_intelligence_graph_edges_target_id', 'intelligence_graph_edges', ['target_id'])
    op.create_index('ix_intelligence_graph_edges_edge_type', 'intelligence_graph_edges', ['edge_type'])
    op.create_index('ix_intelligence_graph_edges_updated_at', 'intelligence_graph_edges', ['updated_at'])

    op.create_table(
        'intelligence_model_registry_states',
        sa.Column('registry_name', sa.String(length=120), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('registry_name'),
    )


def downgrade() -> None:
    op.drop_table('intelligence_model_registry_states')
    op.drop_index('ix_intelligence_graph_edges_updated_at', table_name='intelligence_graph_edges')
    op.drop_index('ix_intelligence_graph_edges_edge_type', table_name='intelligence_graph_edges')
    op.drop_index('ix_intelligence_graph_edges_target_id', table_name='intelligence_graph_edges')
    op.drop_index('ix_intelligence_graph_edges_source_id', table_name='intelligence_graph_edges')
    op.drop_table('intelligence_graph_edges')
    op.drop_index('ix_intelligence_graph_nodes_updated_at', table_name='intelligence_graph_nodes')
    op.drop_index('ix_intelligence_graph_nodes_node_type', table_name='intelligence_graph_nodes')
    op.drop_table('intelligence_graph_nodes')
    op.drop_table('industry_intelligence_models')

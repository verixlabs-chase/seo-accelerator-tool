"""add scaling indexes for concurrency hardening

Revision ID: 20260310_0069
Revises: 20260310_0068
Create Date: 2026-03-10 16:20:00.000000
"""

from __future__ import annotations

from alembic import op


revision = '20260310_0069'
down_revision = '20260310_0068'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        'ix_policy_performance_policy_campaign',
        'policy_performance',
        ['policy_id', 'campaign_id'],
        unique=False,
    )
    op.create_index(
        'ix_experiment_assignments_campaign_policy_created',
        'experiment_assignments',
        ['campaign_id', 'assigned_policy_id', 'created_at'],
        unique=False,
    )
    op.create_index(
        'ix_knowledge_edges_source_type_confidence',
        'knowledge_edges',
        ['source_node_id', 'edge_type', 'confidence'],
        unique=False,
    )
    op.create_index(
        'ix_experiment_outcomes_experiment_measured',
        'experiment_outcomes',
        ['experiment_id', 'measured_at'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_experiment_outcomes_experiment_measured', table_name='experiment_outcomes')
    op.drop_index('ix_knowledge_edges_source_type_confidence', table_name='knowledge_edges')
    op.drop_index('ix_experiment_assignments_campaign_policy_created', table_name='experiment_assignments')
    op.drop_index('ix_policy_performance_policy_campaign', table_name='policy_performance')

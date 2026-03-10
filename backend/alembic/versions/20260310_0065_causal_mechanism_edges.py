"""add causal mechanism graph persistence

Revision ID: 20260310_0065
Revises: 20260310_0064
Create Date: 2026-03-10 05:10:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '20260310_0065'
down_revision = '20260310_0064'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'policy_feature_edges',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('policy_id', sa.String(length=255), nullable=False),
        sa.Column('feature_name', sa.String(length=255), nullable=False),
        sa.Column('effect_size', sa.Float(), nullable=False, server_default='0'),
        sa.Column('confidence', sa.Float(), nullable=False, server_default='0'),
        sa.Column('sample_size', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('industry', sa.String(length=120), nullable=False, server_default='unknown'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('policy_id', 'feature_name', 'industry', name='uq_policy_feature_edge_identity'),
    )
    op.create_index(op.f('ix_policy_feature_edges_policy_id'), 'policy_feature_edges', ['policy_id'], unique=False)
    op.create_index(op.f('ix_policy_feature_edges_feature_name'), 'policy_feature_edges', ['feature_name'], unique=False)
    op.create_index(op.f('ix_policy_feature_edges_industry'), 'policy_feature_edges', ['industry'], unique=False)
    op.create_index('ix_policy_feature_edges_industry_confidence', 'policy_feature_edges', ['industry', 'confidence'], unique=False)

    op.create_table(
        'causal_feature_edges',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('policy_id', sa.String(length=255), nullable=False),
        sa.Column('feature_name', sa.String(length=255), nullable=False),
        sa.Column('outcome_name', sa.String(length=255), nullable=False, server_default='outcome::success'),
        sa.Column('effect_size', sa.Float(), nullable=False, server_default='0'),
        sa.Column('confidence', sa.Float(), nullable=False, server_default='0'),
        sa.Column('sample_size', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('industry', sa.String(length=120), nullable=False, server_default='unknown'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('policy_id', 'feature_name', 'outcome_name', 'industry', name='uq_causal_feature_edge_identity'),
    )
    op.create_index(op.f('ix_causal_feature_edges_policy_id'), 'causal_feature_edges', ['policy_id'], unique=False)
    op.create_index(op.f('ix_causal_feature_edges_feature_name'), 'causal_feature_edges', ['feature_name'], unique=False)
    op.create_index(op.f('ix_causal_feature_edges_outcome_name'), 'causal_feature_edges', ['outcome_name'], unique=False)
    op.create_index(op.f('ix_causal_feature_edges_industry'), 'causal_feature_edges', ['industry'], unique=False)
    op.create_index('ix_causal_feature_edges_industry_confidence', 'causal_feature_edges', ['industry', 'confidence'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_causal_feature_edges_industry_confidence', table_name='causal_feature_edges')
    op.drop_index(op.f('ix_causal_feature_edges_industry'), table_name='causal_feature_edges')
    op.drop_index(op.f('ix_causal_feature_edges_outcome_name'), table_name='causal_feature_edges')
    op.drop_index(op.f('ix_causal_feature_edges_feature_name'), table_name='causal_feature_edges')
    op.drop_index(op.f('ix_causal_feature_edges_policy_id'), table_name='causal_feature_edges')
    op.drop_table('causal_feature_edges')

    op.drop_index('ix_policy_feature_edges_industry_confidence', table_name='policy_feature_edges')
    op.drop_index(op.f('ix_policy_feature_edges_industry'), table_name='policy_feature_edges')
    op.drop_index(op.f('ix_policy_feature_edges_feature_name'), table_name='policy_feature_edges')
    op.drop_index(op.f('ix_policy_feature_edges_policy_id'), table_name='policy_feature_edges')
    op.drop_table('policy_feature_edges')

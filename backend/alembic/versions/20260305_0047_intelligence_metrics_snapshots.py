from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '20260305_0047'
down_revision = '20260305_0046'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'intelligence_metrics_snapshots',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('campaign_id', sa.String(length=36), nullable=False),
        sa.Column('metric_date', sa.Date(), nullable=False),
        sa.Column('signals_processed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('features_computed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('patterns_detected', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('recommendations_generated', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('executions_run', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('positive_outcomes', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('negative_outcomes', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('policy_updates_applied', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('campaign_id', 'metric_date', name='uq_intelligence_metrics_snapshot_campaign_date'),
    )
    op.create_index('ix_intelligence_metrics_snapshots_campaign_id', 'intelligence_metrics_snapshots', ['campaign_id'], unique=False)
    op.create_index('ix_intelligence_metrics_snapshots_metric_date', 'intelligence_metrics_snapshots', ['metric_date'], unique=False)
    op.create_index('ix_intelligence_metrics_snapshots_created_at', 'intelligence_metrics_snapshots', ['created_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_intelligence_metrics_snapshots_created_at', table_name='intelligence_metrics_snapshots')
    op.drop_index('ix_intelligence_metrics_snapshots_metric_date', table_name='intelligence_metrics_snapshots')
    op.drop_index('ix_intelligence_metrics_snapshots_campaign_id', table_name='intelligence_metrics_snapshots')
    op.drop_table('intelligence_metrics_snapshots')

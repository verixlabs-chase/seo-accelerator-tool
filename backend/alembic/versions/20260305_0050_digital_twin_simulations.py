from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '20260305_0050'
down_revision = '20260305_0049'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'digital_twin_simulations',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('campaign_id', sa.String(length=36), nullable=False),
        sa.Column('strategy_actions', sa.JSON(), nullable=False),
        sa.Column('predicted_rank_delta', sa.Float(), nullable=False, server_default='0'),
        sa.Column('predicted_traffic_delta', sa.Float(), nullable=False, server_default='0'),
        sa.Column('confidence', sa.Float(), nullable=False, server_default='0'),
        sa.Column('expected_value', sa.Float(), nullable=False, server_default='0'),
        sa.Column('selected_strategy', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('model_version', sa.String(length=128), nullable=False, server_default='v1'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_digital_twin_simulations_campaign_id', 'digital_twin_simulations', ['campaign_id'], unique=False)
    op.create_index('ix_digital_twin_simulations_created_at', 'digital_twin_simulations', ['created_at'], unique=False)
    op.create_index('ix_digital_twin_simulations_selected_strategy', 'digital_twin_simulations', ['selected_strategy'], unique=False)

    with op.batch_alter_table('intelligence_metrics_snapshots') as batch_op:
        batch_op.add_column(sa.Column('simulations_run', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('avg_predicted_rank_delta', sa.Float(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('avg_confidence', sa.Float(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('optimizer_selection_rate', sa.Float(), nullable=False, server_default='0'))


def downgrade() -> None:
    with op.batch_alter_table('intelligence_metrics_snapshots') as batch_op:
        batch_op.drop_column('optimizer_selection_rate')
        batch_op.drop_column('avg_confidence')
        batch_op.drop_column('avg_predicted_rank_delta')
        batch_op.drop_column('simulations_run')

    op.drop_index('ix_digital_twin_simulations_selected_strategy', table_name='digital_twin_simulations')
    op.drop_index('ix_digital_twin_simulations_created_at', table_name='digital_twin_simulations')
    op.drop_index('ix_digital_twin_simulations_campaign_id', table_name='digital_twin_simulations')
    op.drop_table('digital_twin_simulations')

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '20260305_0051'
down_revision = '20260305_0050'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('recommendation_outcomes') as batch_op:
        batch_op.add_column(sa.Column('simulation_id', sa.String(length=36), nullable=True))
        batch_op.create_index('ix_recommendation_outcomes_simulation_id', ['simulation_id'], unique=False)
        batch_op.create_foreign_key(
            'fk_recommendation_outcomes_simulation_id',
            'digital_twin_simulations',
            ['simulation_id'],
            ['id'],
            ondelete='SET NULL',
        )

    with op.batch_alter_table('intelligence_metrics_snapshots') as batch_op:
        batch_op.add_column(sa.Column('avg_prediction_error_rank', sa.Float(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('avg_prediction_error_traffic', sa.Float(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('prediction_accuracy_score', sa.Float(), nullable=False, server_default='0'))


def downgrade() -> None:
    with op.batch_alter_table('intelligence_metrics_snapshots') as batch_op:
        batch_op.drop_column('prediction_accuracy_score')
        batch_op.drop_column('avg_prediction_error_traffic')
        batch_op.drop_column('avg_prediction_error_rank')

    with op.batch_alter_table('recommendation_outcomes') as batch_op:
        batch_op.drop_constraint('fk_recommendation_outcomes_simulation_id', type_='foreignkey')
        batch_op.drop_index('ix_recommendation_outcomes_simulation_id')
        batch_op.drop_column('simulation_id')

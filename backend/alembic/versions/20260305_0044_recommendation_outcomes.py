from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = '20260305_0044'
down_revision = '20260305_0043'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'recommendation_outcomes',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('recommendation_id', sa.String(length=36), nullable=False),
        sa.Column('campaign_id', sa.String(length=36), nullable=False),
        sa.Column('metric_before', sa.Float(), nullable=False, server_default='0'),
        sa.Column('metric_after', sa.Float(), nullable=False, server_default='0'),
        sa.Column('delta', sa.Float(), nullable=False, server_default='0'),
        sa.Column('measured_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['recommendation_id'], ['strategy_recommendations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_recommendation_outcomes_recommendation_id', 'recommendation_outcomes', ['recommendation_id'], unique=False)
    op.create_index('ix_recommendation_outcomes_campaign_id', 'recommendation_outcomes', ['campaign_id'], unique=False)
    op.create_index('ix_recommendation_outcomes_measured_at', 'recommendation_outcomes', ['measured_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_recommendation_outcomes_measured_at', table_name='recommendation_outcomes')
    op.drop_index('ix_recommendation_outcomes_campaign_id', table_name='recommendation_outcomes')
    op.drop_index('ix_recommendation_outcomes_recommendation_id', table_name='recommendation_outcomes')
    op.drop_table('recommendation_outcomes')

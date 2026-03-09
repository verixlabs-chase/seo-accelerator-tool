"""extend seo flight recorder for causal discovery"""

from alembic import op
import sqlalchemy as sa


revision = '20260309_0057'
down_revision = '20260309_0056'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'seo_mutation_outcomes',
        sa.Column('mutation_parameters', sa.JSON(), nullable=False, server_default='{}'),
    )


def downgrade() -> None:
    op.drop_column('seo_mutation_outcomes', 'mutation_parameters')

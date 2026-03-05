from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = '20260305_0043'
down_revision = '20260304_0030'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'platform_jobs',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('job_type', sa.String(length=120), nullable=False),
        sa.Column('entity_type', sa.String(length=64), nullable=False),
        sa.Column('entity_id', sa.String(length=36), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('result', sa.JSON(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_platform_jobs_job_type', 'platform_jobs', ['job_type'], unique=False)
    op.create_index('ix_platform_jobs_entity_type', 'platform_jobs', ['entity_type'], unique=False)
    op.create_index('ix_platform_jobs_entity_id', 'platform_jobs', ['entity_id'], unique=False)
    op.create_index('ix_platform_jobs_status', 'platform_jobs', ['status'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_platform_jobs_status', table_name='platform_jobs')
    op.drop_index('ix_platform_jobs_entity_id', table_name='platform_jobs')
    op.drop_index('ix_platform_jobs_entity_type', table_name='platform_jobs')
    op.drop_index('ix_platform_jobs_job_type', table_name='platform_jobs')
    op.drop_table('platform_jobs')

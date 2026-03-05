"""add onboarding sessions

Revision ID: 20260304_0030
Revises: 009c09f3c436
Create Date: 2026-03-04 12:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260304_0030"
down_revision = '009c09f3c436'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "onboarding_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=True),
        sa.Column("organization_id", sa.String(length=36), nullable=True),
        sa.Column("campaign_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("current_step", sa.String(length=40), nullable=False),
        sa.Column("step_payload", sa.JSON(), nullable=False),
        sa.Column("error_state", sa.JSON(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_onboarding_sessions_tenant_id", "onboarding_sessions", ["tenant_id"], unique=False)
    op.create_index("ix_onboarding_sessions_organization_id", "onboarding_sessions", ["organization_id"], unique=False)
    op.create_index("ix_onboarding_sessions_campaign_id", "onboarding_sessions", ["campaign_id"], unique=False)
    op.create_index("ix_onboarding_sessions_status", "onboarding_sessions", ["status"], unique=False)
    op.create_index("ix_onboarding_sessions_current_step", "onboarding_sessions", ["current_step"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_onboarding_sessions_current_step", table_name="onboarding_sessions")
    op.drop_index("ix_onboarding_sessions_status", table_name="onboarding_sessions")
    op.drop_index("ix_onboarding_sessions_campaign_id", table_name="onboarding_sessions")
    op.drop_index("ix_onboarding_sessions_organization_id", table_name="onboarding_sessions")
    op.drop_index("ix_onboarding_sessions_tenant_id", table_name="onboarding_sessions")
    op.drop_table("onboarding_sessions")

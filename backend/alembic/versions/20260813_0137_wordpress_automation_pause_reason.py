"""record managed WordPress automation pause reasons

Revision ID: 20260813_0137
Revises: 20260813_0136
Create Date: 2026-08-13 10:05:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260813_0137"
down_revision = "20260813_0136"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "wordpress_automation_policies",
        sa.Column("paused_reason_code", sa.String(80), nullable=True),
    )
    op.add_column(
        "wordpress_automation_policies",
        sa.Column("paused_execution_id", sa.String(36), nullable=True),
    )
    op.add_column(
        "wordpress_automation_policies",
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("wordpress_automation_policies", "paused_at")
    op.drop_column("wordpress_automation_policies", "paused_execution_id")
    op.drop_column("wordpress_automation_policies", "paused_reason_code")

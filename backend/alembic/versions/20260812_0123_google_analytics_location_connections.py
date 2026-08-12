"""add engaged website sessions for location analytics connections

Revision ID: 20260812_0123
Revises: 20260812_0122
Create Date: 2026-08-12 16:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260812_0123"
down_revision = "20260812_0122"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "analytics_daily_metrics",
        sa.Column(
            "engaged_sessions",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("analytics_daily_metrics", "engaged_sessions")

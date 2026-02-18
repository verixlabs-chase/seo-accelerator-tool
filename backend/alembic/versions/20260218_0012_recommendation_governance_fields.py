"""add recommendation governance fields

Revision ID: 20260218_0012
Revises: 20260218_0011
Create Date: 2026-02-18 21:05:00
"""
from alembic import op
import sqlalchemy as sa


revision = "20260218_0012"
down_revision = "20260218_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "strategy_recommendations",
        sa.Column("confidence_score", sa.Float(), nullable=False, server_default="0.7"),
    )
    op.add_column(
        "strategy_recommendations",
        sa.Column("evidence_json", sa.Text(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("strategy_recommendations", "evidence_json")
    op.drop_column("strategy_recommendations", "confidence_score")

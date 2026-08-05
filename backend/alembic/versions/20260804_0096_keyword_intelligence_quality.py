"""record prediction snapshots for measured keyword relevance quality

Revision ID: 20260804_0096
Revises: 20260804_0095
Create Date: 2026-08-04 18:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260804_0096"
down_revision = "20260804_0095"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("keyword_relevance_feedback") as batch_op:
        batch_op.add_column(
            sa.Column("predicted_relevance_status", sa.String(length=24), nullable=True)
        )
        batch_op.add_column(sa.Column("predicted_relevance_score", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("prediction_source", sa.String(length=24), nullable=True))
        batch_op.create_check_constraint(
            "ck_keyword_relevance_feedback_predicted_status",
            "predicted_relevance_status IS NULL OR "
            "predicted_relevance_status in ('relevant','needs_review','unrelated')",
        )
        batch_op.create_check_constraint(
            "ck_keyword_relevance_feedback_predicted_score",
            "predicted_relevance_score IS NULL OR "
            "(predicted_relevance_score >= 0 AND predicted_relevance_score <= 100)",
        )


def downgrade() -> None:
    with op.batch_alter_table("keyword_relevance_feedback") as batch_op:
        batch_op.drop_constraint("ck_keyword_relevance_feedback_predicted_score", type_="check")
        batch_op.drop_constraint("ck_keyword_relevance_feedback_predicted_status", type_="check")
        batch_op.drop_column("prediction_source")
        batch_op.drop_column("predicted_relevance_score")
        batch_op.drop_column("predicted_relevance_status")

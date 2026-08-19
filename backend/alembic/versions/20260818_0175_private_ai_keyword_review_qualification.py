"""add qualification-only private-AI keyword review capability

Revision ID: 20260818_0175
Revises: 20260818_0174
Create Date: 2026-08-18 23:45:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260818_0175"
down_revision = "20260818_0174"
branch_labels = None
depends_on = None


BENCHMARKS = "governed_ai_provider_capability_benchmarks"


def upgrade() -> None:
    with op.batch_alter_table(BENCHMARKS) as batch:
        batch.drop_constraint(
            "ck_ai_provider_capability_benchmark_scope", type_="check"
        )
        batch.create_check_constraint(
            "ck_ai_provider_capability_benchmark_scope",
            "capability in ('intelligence_question','intelligence_draft',"
            "'keyword_relevance_review') AND case_count = 1",
        )


def downgrade() -> None:
    _ensure_no_keyword_review_benchmarks()
    with op.batch_alter_table(BENCHMARKS) as batch:
        batch.drop_constraint(
            "ck_ai_provider_capability_benchmark_scope", type_="check"
        )
        batch.create_check_constraint(
            "ck_ai_provider_capability_benchmark_scope",
            "capability in ('intelligence_question','intelligence_draft') "
            "AND case_count = 1",
        )


def _ensure_no_keyword_review_benchmarks() -> None:
    connection = op.get_bind()
    count = connection.execute(
        sa.text(
            f"SELECT COUNT(*) FROM {BENCHMARKS} "
            "WHERE capability = 'keyword_relevance_review'"
        )
    ).scalar_one()
    if count:
        raise RuntimeError(
            "Cannot downgrade while private-AI keyword-review qualification history "
            "exists; preserve the immutable evidence or remove it through an approved "
            "platform-maintenance procedure."
        )

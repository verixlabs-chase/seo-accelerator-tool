"""add qualification-only private-AI review response drafting capability

Revision ID: 20260819_0181
Revises: 20260819_0180
Create Date: 2026-08-19 02:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260819_0181"
down_revision = "20260819_0180"
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
            "'keyword_relevance_review','content_draft_suggestion',"
            "'onboarding_baseline_narrative','review_response_draft') "
            "AND case_count = 1",
        )


def downgrade() -> None:
    _ensure_no_review_response_benchmarks()
    with op.batch_alter_table(BENCHMARKS) as batch:
        batch.drop_constraint(
            "ck_ai_provider_capability_benchmark_scope", type_="check"
        )
        batch.create_check_constraint(
            "ck_ai_provider_capability_benchmark_scope",
            "capability in ('intelligence_question','intelligence_draft',"
            "'keyword_relevance_review','content_draft_suggestion',"
            "'onboarding_baseline_narrative') AND case_count = 1",
        )


def _ensure_no_review_response_benchmarks() -> None:
    connection = op.get_bind()
    count = connection.execute(
        sa.text(
            f"SELECT COUNT(*) FROM {BENCHMARKS} "
            "WHERE capability = 'review_response_draft'"
        )
    ).scalar_one()
    if count:
        raise RuntimeError(
            "Cannot downgrade while private-AI review-response qualification "
            "history exists; preserve the immutable evidence or remove it through "
            "an approved platform-maintenance procedure."
        )

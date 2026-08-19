"""add qualification-only private-AI content draft suggestion capability

Revision ID: 20260818_0177
Revises: 20260818_0176
Create Date: 2026-08-18 23:59:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260818_0177"
down_revision = "20260818_0176"
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
            "'keyword_relevance_review','content_draft_suggestion') "
            "AND case_count = 1",
        )


def downgrade() -> None:
    _ensure_no_content_draft_benchmarks()
    with op.batch_alter_table(BENCHMARKS) as batch:
        batch.drop_constraint(
            "ck_ai_provider_capability_benchmark_scope", type_="check"
        )
        batch.create_check_constraint(
            "ck_ai_provider_capability_benchmark_scope",
            "capability in ('intelligence_question','intelligence_draft',"
            "'keyword_relevance_review') AND case_count = 1",
        )


def _ensure_no_content_draft_benchmarks() -> None:
    connection = op.get_bind()
    count = connection.execute(
        sa.text(
            f"SELECT COUNT(*) FROM {BENCHMARKS} "
            "WHERE capability = 'content_draft_suggestion'"
        )
    ).scalar_one()
    if count:
        raise RuntimeError(
            "Cannot downgrade while private-AI content-draft qualification history "
            "exists; preserve the immutable evidence or remove it through an approved "
            "platform-maintenance procedure."
        )

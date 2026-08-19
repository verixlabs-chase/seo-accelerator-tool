"""add governed private-AI draft wording capability

Revision ID: 20260818_0174
Revises: 20260818_0173
Create Date: 2026-08-18 23:10:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260818_0174"
down_revision = "20260818_0173"
branch_labels = None
depends_on = None


BENCHMARKS = "governed_ai_provider_capability_benchmarks"
EVENTS = "governed_ai_provider_capability_events"
ATTEMPTS = "governed_ai_provider_capability_attempts"


def upgrade() -> None:
    with op.batch_alter_table(BENCHMARKS) as batch:
        batch.drop_constraint(
            "ck_ai_provider_capability_benchmark_scope", type_="check"
        )
        batch.create_check_constraint(
            "ck_ai_provider_capability_benchmark_scope",
            "capability in ('intelligence_question','intelligence_draft') "
            "AND case_count = 1",
        )
    with op.batch_alter_table(EVENTS) as batch:
        batch.drop_constraint("ck_ai_provider_capability_event_scope", type_="check")
        batch.create_check_constraint(
            "ck_ai_provider_capability_event_scope",
            "capability in ('intelligence_question','intelligence_draft') "
            "AND max_prompts_per_day = 1",
        )
    with op.batch_alter_table(ATTEMPTS) as batch:
        batch.drop_constraint(
            "ck_ai_provider_capability_attempt_scope", type_="check"
        )
        batch.create_check_constraint(
            "ck_ai_provider_capability_attempt_scope",
            "capability in ('intelligence_question','intelligence_draft') "
            "AND customer_prompt_sent = true "
            "AND automatic_changes_allowed = false AND platform_provider_cost = 0",
        )


def downgrade() -> None:
    _ensure_no_draft_capability_rows()
    with op.batch_alter_table(ATTEMPTS) as batch:
        batch.drop_constraint(
            "ck_ai_provider_capability_attempt_scope", type_="check"
        )
        batch.create_check_constraint(
            "ck_ai_provider_capability_attempt_scope",
            "capability = 'intelligence_question' AND customer_prompt_sent = true "
            "AND automatic_changes_allowed = false AND platform_provider_cost = 0",
        )
    with op.batch_alter_table(EVENTS) as batch:
        batch.drop_constraint("ck_ai_provider_capability_event_scope", type_="check")
        batch.create_check_constraint(
            "ck_ai_provider_capability_event_scope",
            "capability = 'intelligence_question' AND max_prompts_per_day = 1",
        )
    with op.batch_alter_table(BENCHMARKS) as batch:
        batch.drop_constraint(
            "ck_ai_provider_capability_benchmark_scope", type_="check"
        )
        batch.create_check_constraint(
            "ck_ai_provider_capability_benchmark_scope",
            "capability = 'intelligence_question' AND case_count = 1",
        )


def _ensure_no_draft_capability_rows() -> None:
    connection = op.get_bind()
    for table in (ATTEMPTS, EVENTS, BENCHMARKS):
        count = connection.execute(
            sa.text(
                f"SELECT COUNT(*) FROM {table} "
                "WHERE capability = 'intelligence_draft'"
            )
        ).scalar_one()
        if count:
            raise RuntimeError(
                "Cannot downgrade while private-AI draft capability history exists; "
                "preserve the immutable evidence or remove it through an approved "
                "platform-maintenance procedure."
            )

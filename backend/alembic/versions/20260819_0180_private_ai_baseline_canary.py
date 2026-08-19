"""add governed private-AI onboarding baseline explanation canary

Revision ID: 20260819_0180
Revises: 20260819_0179
Create Date: 2026-08-19 01:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260819_0180"
down_revision = "20260819_0179"
branch_labels = None
depends_on = None


EVENTS = "governed_ai_provider_capability_events"
ATTEMPTS = "governed_ai_provider_capability_attempts"


def upgrade() -> None:
    with op.batch_alter_table(EVENTS) as batch:
        batch.drop_constraint("ck_ai_provider_capability_event_scope", type_="check")
        batch.create_check_constraint(
            "ck_ai_provider_capability_event_scope",
            "capability in ('intelligence_question','intelligence_draft',"
            "'keyword_relevance_review','content_draft_suggestion',"
            "'onboarding_baseline_narrative') AND max_prompts_per_day = 1",
        )
    with op.batch_alter_table(ATTEMPTS) as batch:
        batch.drop_constraint(
            "ck_ai_provider_capability_attempt_scope", type_="check"
        )
        batch.create_check_constraint(
            "ck_ai_provider_capability_attempt_scope",
            "capability in ('intelligence_question','intelligence_draft',"
            "'keyword_relevance_review','content_draft_suggestion',"
            "'onboarding_baseline_narrative') AND customer_prompt_sent = true "
            "AND automatic_changes_allowed = false AND platform_provider_cost = 0",
        )


def downgrade() -> None:
    _ensure_no_baseline_runtime_rows()
    with op.batch_alter_table(ATTEMPTS) as batch:
        batch.drop_constraint(
            "ck_ai_provider_capability_attempt_scope", type_="check"
        )
        batch.create_check_constraint(
            "ck_ai_provider_capability_attempt_scope",
            "capability in ('intelligence_question','intelligence_draft',"
            "'keyword_relevance_review','content_draft_suggestion') "
            "AND customer_prompt_sent = true "
            "AND automatic_changes_allowed = false AND platform_provider_cost = 0",
        )
    with op.batch_alter_table(EVENTS) as batch:
        batch.drop_constraint("ck_ai_provider_capability_event_scope", type_="check")
        batch.create_check_constraint(
            "ck_ai_provider_capability_event_scope",
            "capability in ('intelligence_question','intelligence_draft',"
            "'keyword_relevance_review','content_draft_suggestion') "
            "AND max_prompts_per_day = 1",
        )


def _ensure_no_baseline_runtime_rows() -> None:
    connection = op.get_bind()
    for table in (ATTEMPTS, EVENTS):
        count = connection.execute(
            sa.text(
                f"SELECT COUNT(*) FROM {table} "
                "WHERE capability = 'onboarding_baseline_narrative'"
            )
        ).scalar_one()
        if count:
            raise RuntimeError(
                "Cannot downgrade while private-AI onboarding-baseline canary history "
                "exists; preserve the immutable evidence or remove it through an "
                "approved platform-maintenance procedure."
            )

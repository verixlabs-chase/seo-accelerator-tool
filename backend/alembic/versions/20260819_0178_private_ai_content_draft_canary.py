"""add governed private-AI website draft suggestion canary

Revision ID: 20260819_0178
Revises: 20260818_0177
Create Date: 2026-08-19 00:10:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260819_0178"
down_revision = "20260818_0177"
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
            "'keyword_relevance_review','content_draft_suggestion') "
            "AND max_prompts_per_day = 1",
        )
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


def downgrade() -> None:
    _ensure_no_content_draft_runtime_rows()
    with op.batch_alter_table(ATTEMPTS) as batch:
        batch.drop_constraint(
            "ck_ai_provider_capability_attempt_scope", type_="check"
        )
        batch.create_check_constraint(
            "ck_ai_provider_capability_attempt_scope",
            "capability in ('intelligence_question','intelligence_draft',"
            "'keyword_relevance_review') AND customer_prompt_sent = true "
            "AND automatic_changes_allowed = false AND platform_provider_cost = 0",
        )
    with op.batch_alter_table(EVENTS) as batch:
        batch.drop_constraint("ck_ai_provider_capability_event_scope", type_="check")
        batch.create_check_constraint(
            "ck_ai_provider_capability_event_scope",
            "capability in ('intelligence_question','intelligence_draft',"
            "'keyword_relevance_review') AND max_prompts_per_day = 1",
        )


def _ensure_no_content_draft_runtime_rows() -> None:
    connection = op.get_bind()
    for table in (ATTEMPTS, EVENTS):
        count = connection.execute(
            sa.text(
                f"SELECT COUNT(*) FROM {table} "
                "WHERE capability = 'content_draft_suggestion'"
            )
        ).scalar_one()
        if count:
            raise RuntimeError(
                "Cannot downgrade while private-AI content-draft canary history "
                "exists; preserve the immutable evidence or remove it through an "
                "approved platform-maintenance procedure."
            )

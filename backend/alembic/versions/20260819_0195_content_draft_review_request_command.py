"""add governed content draft review request command

Revision ID: 20260819_0195
Revises: 20260819_0194
Create Date: 2026-08-19 23:58:00.000000
"""

from __future__ import annotations

import json

from alembic import op
import sqlalchemy as sa


revision = "20260819_0195"
down_revision = "20260819_0194"
branch_labels = None
depends_on = None

TABLE = "automation_command_receipts"
CONSTRAINT = "ck_automation_command_receipts_type"
COMMAND = "content.request_draft_review"


def upgrade() -> None:
    with op.batch_alter_table(TABLE) as batch:
        batch.drop_constraint(CONSTRAINT, type_="check")
        batch.create_check_constraint(
            CONSTRAINT,
            "command_type in ('report.retrieve','report.generate_saved','recommendation.retrieve','recommendation.request_review','connection.refresh_saved','listing.check_public','content.create_working_draft','content.request_draft_review')",
        )


def downgrade() -> None:
    bind = op.get_bind()
    receipt = bind.execute(
        sa.text(f"SELECT 1 FROM {TABLE} WHERE command_type = :command LIMIT 1"),
        {"command": COMMAND},
    ).first()
    accounts = bind.execute(
        sa.text("SELECT allowed_commands_json FROM automation_service_accounts")
    ).all()
    if receipt is not None or any(COMMAND in _commands(row[0]) for row in accounts):
        raise RuntimeError(
            "Cannot downgrade while draft-review command data exists. "
            "Revoke expanded keys and remove review receipts through approved maintenance first."
        )
    with op.batch_alter_table(TABLE) as batch:
        batch.drop_constraint(CONSTRAINT, type_="check")
        batch.create_check_constraint(
            CONSTRAINT,
            "command_type in ('report.retrieve','report.generate_saved','recommendation.retrieve','recommendation.request_review','connection.refresh_saved','listing.check_public','content.create_working_draft')",
        )


def _commands(raw: str) -> set[str]:
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return set()
    return {str(item) for item in value} if isinstance(value, list) else set()

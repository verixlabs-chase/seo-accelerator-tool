"""add saved-data report generation automation command

Revision ID: 20260819_0189
Revises: 20260819_0188
Create Date: 2026-08-19 17:00:00.000000
"""

from __future__ import annotations

import json

from alembic import op
import sqlalchemy as sa


revision = "20260819_0189"
down_revision = "20260819_0188"
branch_labels = None
depends_on = None

TABLE = "automation_command_receipts"
CONSTRAINT = "ck_automation_command_receipts_type"
NEW_COMMAND = "report.generate_saved"


def upgrade() -> None:
    with op.batch_alter_table(TABLE) as batch:
        batch.drop_constraint(CONSTRAINT, type_="check")
        batch.alter_column("report_id", existing_type=sa.String(36), nullable=True)
        batch.create_check_constraint(
            CONSTRAINT,
            "command_type in ('report.retrieve','report.generate_saved')",
        )


def downgrade() -> None:
    bind = op.get_bind()
    generated_receipt = bind.execute(
        sa.text(
            f"SELECT 1 FROM {TABLE} WHERE command_type = :command_type LIMIT 1"
        ),
        {"command_type": NEW_COMMAND},
    ).first()
    account_rows = bind.execute(
        sa.text("SELECT allowed_commands_json FROM automation_service_accounts")
    ).all()
    expanded_account = any(
        NEW_COMMAND in _commands(row[0]) for row in account_rows
    )
    if generated_receipt is not None or expanded_account:
        raise RuntimeError(
            "Cannot downgrade while saved-report generation command data exists. "
            "Revoke expanded workflow keys and remove command receipts under an "
            "approved maintenance procedure first."
        )
    with op.batch_alter_table(TABLE) as batch:
        batch.drop_constraint(CONSTRAINT, type_="check")
        batch.alter_column("report_id", existing_type=sa.String(36), nullable=False)
        batch.create_check_constraint(
            CONSTRAINT,
            "command_type in ('report.retrieve')",
        )


def _commands(raw: str) -> set[str]:
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return set()
    return {str(item) for item in value} if isinstance(value, list) else set()

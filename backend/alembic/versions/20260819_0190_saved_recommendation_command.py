"""add scoped saved-recommendation retrieval command

Revision ID: 20260819_0190
Revises: 20260819_0189
Create Date: 2026-08-19 18:30:00.000000
"""

from __future__ import annotations

import json

from alembic import op
import sqlalchemy as sa


revision = "20260819_0190"
down_revision = "20260819_0189"
branch_labels = None
depends_on = None

RECEIPT_TABLE = "automation_command_receipts"
RECOMMENDATION_TABLE = "strategy_recommendations"
TYPE_CONSTRAINT = "ck_automation_command_receipts_type"
SCOPE_UNIQUE = "uq_strategy_recommendations_id_scope"
SCOPE_FK = "fk_automation_command_receipts_recommendation_scope"
NEW_COMMAND = "recommendation.retrieve"


def upgrade() -> None:
    with op.batch_alter_table(RECOMMENDATION_TABLE) as batch:
        batch.create_unique_constraint(
            SCOPE_UNIQUE, ["id", "tenant_id", "campaign_id"]
        )
    with op.batch_alter_table(RECEIPT_TABLE) as batch:
        batch.drop_constraint(TYPE_CONSTRAINT, type_="check")
        batch.add_column(sa.Column("recommendation_id", sa.String(36), nullable=True))
        batch.create_foreign_key(
            SCOPE_FK,
            RECOMMENDATION_TABLE,
            ["recommendation_id", "tenant_id", "campaign_id"],
            ["id", "tenant_id", "campaign_id"],
            ondelete="RESTRICT",
        )
        batch.create_check_constraint(
            TYPE_CONSTRAINT,
            "command_type in ('report.retrieve','report.generate_saved','recommendation.retrieve')",
        )


def downgrade() -> None:
    bind = op.get_bind()
    receipt = bind.execute(
        sa.text(
            f"SELECT 1 FROM {RECEIPT_TABLE} WHERE command_type = :command_type LIMIT 1"
        ),
        {"command_type": NEW_COMMAND},
    ).first()
    accounts = bind.execute(
        sa.text("SELECT allowed_commands_json FROM automation_service_accounts")
    ).all()
    if receipt is not None or any(NEW_COMMAND in _commands(row[0]) for row in accounts):
        raise RuntimeError(
            "Cannot downgrade while saved-recommendation command data exists. "
            "Revoke expanded workflow keys and remove command receipts under an "
            "approved maintenance procedure first."
        )
    with op.batch_alter_table(RECEIPT_TABLE) as batch:
        batch.drop_constraint(TYPE_CONSTRAINT, type_="check")
        batch.drop_constraint(SCOPE_FK, type_="foreignkey")
        batch.drop_column("recommendation_id")
        batch.create_check_constraint(
            TYPE_CONSTRAINT,
            "command_type in ('report.retrieve','report.generate_saved')",
        )
    with op.batch_alter_table(RECOMMENDATION_TABLE) as batch:
        batch.drop_constraint(SCOPE_UNIQUE, type_="unique")


def _commands(raw: str) -> set[str]:
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return set()
    return {str(item) for item in value} if isinstance(value, list) else set()

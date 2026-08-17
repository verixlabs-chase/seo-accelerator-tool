"""add governed n8n Cloud webhook destinations

Revision ID: 20260817_0162
Revises: 20260816_0161
Create Date: 2026-08-17 10:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260817_0162"
down_revision = "20260816_0161"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("automation_webhook_connections") as batch_op:
        batch_op.drop_constraint(
            "ck_automation_webhook_connections_provider", type_="check"
        )
        batch_op.create_check_constraint(
            "ck_automation_webhook_connections_provider",
            "provider in ('zapier','make','pipedream','n8n')",
        )


def downgrade() -> None:
    bind = op.get_bind()
    n8n_connections = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM automation_webhook_connections "
            "WHERE provider = 'n8n'"
        )
    ).scalar_one()
    if int(n8n_connections or 0) > 0:
        raise RuntimeError(
            "Cannot downgrade n8n Cloud support while an n8n connection exists. "
            "Disconnect and preserve those connection records before retrying."
        )
    with op.batch_alter_table("automation_webhook_connections") as batch_op:
        batch_op.drop_constraint(
            "ck_automation_webhook_connections_provider", type_="check"
        )
        batch_op.create_check_constraint(
            "ck_automation_webhook_connections_provider",
            "provider in ('zapier','make','pipedream')",
        )

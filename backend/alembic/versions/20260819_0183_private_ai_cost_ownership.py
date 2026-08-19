"""make private-AI connection cost ownership explicit

Revision ID: 20260819_0183
Revises: 20260819_0182
Create Date: 2026-08-19 04:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260819_0183"
down_revision = "20260819_0182"
branch_labels = None
depends_on = None


TABLE = "governed_ai_provider_connections"
CONSTRAINT = "ck_governed_ai_provider_connections_cost_owner"


def upgrade() -> None:
    with op.batch_alter_table(TABLE) as batch:
        batch.add_column(
            sa.Column(
                "credential_owner",
                sa.String(length=20),
                nullable=False,
                server_default="organization",
            )
        )
        batch.add_column(
            sa.Column(
                "cost_responsibility",
                sa.String(length=20),
                nullable=False,
                server_default="customer",
            )
        )
        batch.add_column(
            sa.Column(
                "platform_billing_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
        batch.create_check_constraint(
            CONSTRAINT,
            "credential_owner = 'organization' "
            "AND cost_responsibility = 'customer' "
            "AND platform_billing_enabled = false",
        )


def downgrade() -> None:
    with op.batch_alter_table(TABLE) as batch:
        batch.drop_constraint(CONSTRAINT, type_="check")
        batch.drop_column("platform_billing_enabled")
        batch.drop_column("cost_responsibility")
        batch.drop_column("credential_owner")

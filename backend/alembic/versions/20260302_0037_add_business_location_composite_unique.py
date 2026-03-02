"""add business location composite unique constraint

Revision ID: 20260302_0037
Revises: 20260302_0036
Create Date: 2026-03-02
"""

from __future__ import annotations

from alembic import context
from alembic import op


revision = "20260302_0037"
down_revision = "20260302_0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    offline = context.is_offline_mode()
    _ = offline

    with op.batch_alter_table("business_locations") as batch_op:
        batch_op.create_unique_constraint(
            "uq_business_locations_id_org",
            ["id", "organization_id"],
        )


def downgrade() -> None:
    offline = context.is_offline_mode()
    _ = offline

    with op.batch_alter_table("business_locations") as batch_op:
        batch_op.drop_constraint(
            "uq_business_locations_id_org",
            type_="unique",
        )

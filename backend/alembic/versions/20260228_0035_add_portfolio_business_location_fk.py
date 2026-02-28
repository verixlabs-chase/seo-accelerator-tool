"""add portfolio business location fk

Revision ID: 20260228_0035
Revises: 20260228_0034
Create Date: 2026-02-28 14:40:00
"""

from __future__ import annotations

from alembic import context
from alembic import op
import sqlalchemy as sa


revision = "20260228_0035"
down_revision = "20260228_0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    offline = context.is_offline_mode()
    _ = offline

    with op.batch_alter_table("portfolios") as batch_op:
        batch_op.add_column(sa.Column("business_location_id", sa.String(length=36), nullable=True))
    with op.batch_alter_table("portfolios") as batch_op:
        batch_op.create_foreign_key(
            "fk_portfolios_business_location_id",
            "business_locations",
            ["business_location_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index(
        "ix_portfolios_business_location_id",
        "portfolios",
        ["business_location_id"],
        unique=False,
    )


def downgrade() -> None:
    offline = context.is_offline_mode()
    _ = offline

    op.drop_index("ix_portfolios_business_location_id", table_name="portfolios")
    with op.batch_alter_table("portfolios") as batch_op:
        batch_op.drop_constraint("fk_portfolios_business_location_id", type_="foreignkey")
    with op.batch_alter_table("portfolios") as batch_op:
        batch_op.drop_column("business_location_id")

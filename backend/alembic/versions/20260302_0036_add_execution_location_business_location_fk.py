"""add execution location business_location_id fk

Revision ID: 20260302_0036
Revises: 20260228_0035
Create Date: 2026-03-02
"""

from __future__ import annotations

from alembic import context
from alembic import op
import sqlalchemy as sa


revision = "20260302_0036"
down_revision = "20260228_0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    offline = context.is_offline_mode()
    _ = offline

    with op.batch_alter_table("locations") as batch_op:
        batch_op.add_column(
            sa.Column("business_location_id", sa.String(length=36), nullable=True)
        )

    with op.batch_alter_table("locations") as batch_op:
        batch_op.create_foreign_key(
            "fk_locations_business_location_id",
            "business_locations",
            ["business_location_id"],
            ["id"],
            ondelete="SET NULL",
        )

    op.create_index(
        "ix_locations_business_location_id",
        "locations",
        ["business_location_id"],
        unique=False,
    )


def downgrade() -> None:
    offline = context.is_offline_mode()
    _ = offline

    op.drop_index("ix_locations_business_location_id", table_name="locations")

    with op.batch_alter_table("locations") as batch_op:
        batch_op.drop_constraint(
            "fk_locations_business_location_id",
            type_="foreignkey",
        )

    with op.batch_alter_table("locations") as batch_op:
        batch_op.drop_column("business_location_id")

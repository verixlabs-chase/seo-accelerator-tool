"""enforce business location org alignment composite fk

Revision ID: 20260302_0038
Revises: 20260302_0037
Create Date: 2026-03-02
"""

from __future__ import annotations

from alembic import context
from alembic import op


revision = "20260302_0038"
down_revision = "20260302_0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    offline = context.is_offline_mode()
    _ = offline

    with op.batch_alter_table("locations") as batch_op:
        batch_op.drop_constraint(
            "fk_locations_business_location_id",
            type_="foreignkey",
        )

    with op.batch_alter_table("locations") as batch_op:
        batch_op.create_foreign_key(
            "fk_locations_bl_org_alignment",
            "business_locations",
            ["business_location_id", "organization_id"],
            ["id", "organization_id"],
        )


def downgrade() -> None:
    offline = context.is_offline_mode()
    _ = offline

    with op.batch_alter_table("locations") as batch_op:
        batch_op.drop_constraint(
            "fk_locations_bl_org_alignment",
            type_="foreignkey",
        )

    with op.batch_alter_table("locations") as batch_op:
        batch_op.create_foreign_key(
            "fk_locations_business_location_id",
            "business_locations",
            ["business_location_id"],
            ["id"],
            ondelete="SET NULL",
        )

"""add owner-drawn service-area boundaries

Revision ID: 20260804_0093
Revises: 20260804_0092
Create Date: 2026-08-04 14:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260804_0093"
down_revision = "20260804_0092"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("business_service_areas") as batch_op:
        batch_op.add_column(sa.Column("boundary_points", sa.JSON(), nullable=True))
        batch_op.drop_constraint("ck_business_service_areas_type", type_="check")
        batch_op.create_check_constraint(
            "ck_business_service_areas_type",
            "area_type in ('city','postal_code','county','radius','boundary')",
        )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM business_service_areas WHERE area_type = 'boundary'"))
    with op.batch_alter_table("business_service_areas") as batch_op:
        batch_op.drop_constraint("ck_business_service_areas_type", type_="check")
        batch_op.create_check_constraint(
            "ck_business_service_areas_type",
            "area_type in ('city','postal_code','county','radius')",
        )
        batch_op.drop_column("boundary_points")

"""add road travel-time service-area boundaries

Revision ID: 20260804_0094
Revises: 20260804_0093
Create Date: 2026-08-04 16:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260804_0094"
down_revision = "20260804_0093"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("business_service_areas") as batch_op:
        batch_op.add_column(sa.Column("travel_minutes", sa.Float(), nullable=True))
        batch_op.drop_constraint("ck_business_service_areas_type", type_="check")
        batch_op.create_check_constraint(
            "ck_business_service_areas_type",
            "area_type in ('city','postal_code','county','radius','boundary','drive_time')",
        )
        batch_op.create_check_constraint(
            "ck_business_service_areas_travel_minutes",
            "(area_type = 'drive_time' and travel_minutes between 10 and 90) "
            "or (area_type <> 'drive_time' and travel_minutes is null)",
        )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM business_service_areas WHERE area_type = 'drive_time'"))
    with op.batch_alter_table("business_service_areas") as batch_op:
        batch_op.drop_constraint(
            "ck_business_service_areas_travel_minutes", type_="check"
        )
        batch_op.drop_constraint("ck_business_service_areas_type", type_="check")
        batch_op.create_check_constraint(
            "ck_business_service_areas_type",
            "area_type in ('city','postal_code','county','radius','boundary')",
        )
        batch_op.drop_column("travel_minutes")

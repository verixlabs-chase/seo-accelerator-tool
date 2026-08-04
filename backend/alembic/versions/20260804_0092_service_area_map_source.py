"""allow map evidence for service-area suggestions

Revision ID: 20260804_0092
Revises: 20260804_0091
Create Date: 2026-08-04 13:00:00.000000
"""

from __future__ import annotations

from alembic import op


revision = "20260804_0092"
down_revision = "20260804_0091"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("business_service_areas") as batch_op:
        batch_op.drop_constraint("ck_business_service_areas_source", type_="check")
        batch_op.create_check_constraint(
            "ck_business_service_areas_source",
            "source in ('manual','website','location','business_profile','map')",
        )


def downgrade() -> None:
    with op.batch_alter_table("business_service_areas") as batch_op:
        batch_op.drop_constraint("ck_business_service_areas_source", type_="check")
        batch_op.create_check_constraint(
            "ck_business_service_areas_source",
            "source in ('manual','website','location','business_profile')",
        )

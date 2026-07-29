"""add structured geography and provider location metadata

Revision ID: 20260729_0074
Revises: 20260728_0073
Create Date: 2026-07-29 10:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260729_0074"
down_revision = "20260728_0073"
branch_labels = None
depends_on = None


_COLUMNS = (
    sa.Column("city", sa.String(length=120), nullable=True),
    sa.Column("region", sa.String(length=120), nullable=True),
    sa.Column("country_code", sa.String(length=2), nullable=False, server_default="US"),
    sa.Column("address_line1", sa.String(length=255), nullable=True),
    sa.Column("postal_code", sa.String(length=32), nullable=True),
    sa.Column("latitude", sa.Numeric(9, 6), nullable=True),
    sa.Column("longitude", sa.Numeric(9, 6), nullable=True),
    sa.Column("coordinate_precision", sa.String(length=30), nullable=True),
    sa.Column("coordinate_source", sa.String(length=50), nullable=True),
    sa.Column("provider_location_code", sa.String(length=32), nullable=True),
    sa.Column("provider_location_name", sa.String(length=255), nullable=True),
    sa.Column("provider_location_type", sa.String(length=50), nullable=True),
    sa.Column("provider_location_resolved_at", sa.DateTime(timezone=True), nullable=True),
)


def upgrade() -> None:
    for column in _COLUMNS:
        op.add_column("business_locations", column)

    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            UPDATE business_locations
            SET city = primary_city
            WHERE city IS NULL
              AND primary_city IS NOT NULL
            """
        )
    )
    op.create_index(
        "ix_business_locations_provider_location_code",
        "business_locations",
        ["provider_location_code"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_business_locations_provider_location_code",
        table_name="business_locations",
    )
    for column in reversed(_COLUMNS):
        op.drop_column("business_locations", column.name)

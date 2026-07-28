"""connect subaccounts, business locations, and campaigns

Revision ID: 20260728_0072
Revises: 20260310_0071
Create Date: 2026-07-28 14:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260728_0072"
down_revision = "20260310_0071"
branch_labels = None
depends_on = None


def upgrade() -> None:
    business_location_column = sa.Column(
        "sub_account_id",
        sa.String(length=36),
        sa.ForeignKey(
            "sub_accounts.id",
            name="fk_business_locations_sub_account_id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )
    campaign_column = sa.Column(
        "business_location_id",
        sa.String(length=36),
        sa.ForeignKey(
            "business_locations.id",
            name="fk_campaigns_business_location_id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("business_locations", recreate="always") as batch_op:
            batch_op.add_column(business_location_column)
        with op.batch_alter_table("campaigns", recreate="always") as batch_op:
            batch_op.add_column(campaign_column)
    else:
        op.add_column("business_locations", business_location_column)
        op.add_column("campaigns", campaign_column)

    op.create_index(
        "ix_business_locations_sub_account_id",
        "business_locations",
        ["sub_account_id"],
        unique=False,
    )
    op.create_index(
        "ix_campaigns_business_location_id",
        "campaigns",
        ["business_location_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_campaigns_business_location_id", table_name="campaigns")
    op.drop_index("ix_business_locations_sub_account_id", table_name="business_locations")

    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("campaigns", recreate="always") as batch_op:
            batch_op.drop_column("business_location_id")
        with op.batch_alter_table("business_locations", recreate="always") as batch_op:
            batch_op.drop_column("sub_account_id")
    else:
        op.drop_column("campaigns", "business_location_id")
        op.drop_column("business_locations", "sub_account_id")

"""add tenant and campaign lifecycle states

Revision ID: 20260218_0013
Revises: 20260218_0012
Create Date: 2026-02-18 22:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = "20260218_0013"
down_revision = "20260218_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("tenants") as batch_op:
        batch_op.add_column(sa.Column("status", sa.String(length=20), nullable=False, server_default="Active"))
        batch_op.create_index("ix_tenants_status", ["status"])
        batch_op.create_check_constraint(
            "ck_tenants_status_values",
            "status IN ('Active', 'Suspended', 'Cancelled', 'Archived')",
        )

    with op.batch_alter_table("campaigns") as batch_op:
        batch_op.add_column(sa.Column("setup_state", sa.String(length=30), nullable=False, server_default="Draft"))
        batch_op.create_index("ix_campaigns_setup_state", ["setup_state"])
        batch_op.create_check_constraint(
            "ck_campaigns_setup_state_values",
            "setup_state IN ('Draft', 'Configured', 'BaselineRunning', 'Active', 'Paused')",
        )


def downgrade() -> None:
    with op.batch_alter_table("campaigns") as batch_op:
        batch_op.drop_constraint("ck_campaigns_setup_state_values", type_="check")
        batch_op.drop_index("ix_campaigns_setup_state")
        batch_op.drop_column("setup_state")

    with op.batch_alter_table("tenants") as batch_op:
        batch_op.drop_constraint("ck_tenants_status_values", type_="check")
        batch_op.drop_index("ix_tenants_status")
        batch_op.drop_column("status")

"""add durable deletion authorization evidence

Revision ID: 20260813_0146
Revises: 20260813_0145
Create Date: 2026-08-13 23:05:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260813_0146"
down_revision = "20260813_0145"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("organization_closure_requests") as batch_op:
        batch_op.add_column(
            sa.Column(
                "deletion_authorization_version",
                sa.String(40),
                nullable=False,
                server_default="gov1d.delete.v1",
            )
        )
        batch_op.add_column(
            sa.Column(
                "data_export_choice_acknowledged",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
        batch_op.add_column(
            sa.Column(
                "recovery_window_acknowledged",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
        batch_op.add_column(
            sa.Column("deletion_authorized_at", sa.DateTime(timezone=True), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("organization_closure_requests") as batch_op:
        batch_op.drop_column("deletion_authorized_at")
        batch_op.drop_column("recovery_window_acknowledged")
        batch_op.drop_column("data_export_choice_acknowledged")
        batch_op.drop_column("deletion_authorization_version")

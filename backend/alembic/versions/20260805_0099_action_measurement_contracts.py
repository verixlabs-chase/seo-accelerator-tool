"""add versioned action measurement contracts

Revision ID: 20260805_0099
Revises: 20260805_0098
Create Date: 2026-08-05 15:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260805_0099"
down_revision = "20260805_0098"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "action_plan_measurements",
        sa.Column(
            "result_classification",
            sa.String(40),
            nullable=False,
            server_default="waiting_for_results",
        ),
    )
    op.add_column(
        "action_plan_measurements",
        sa.Column(
            "measurement_contract",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )
    with op.batch_alter_table("action_plan_measurements") as batch_op:
        batch_op.create_check_constraint(
            "ck_action_plan_measurements_result_classification",
            "result_classification in ('waiting_for_results','improved','about_the_same','worse','not_enough_information')",
        )
    op.create_index(
        "ix_action_plan_measurements_result_classification",
        "action_plan_measurements",
        ["result_classification"],
    )
    op.execute(
        sa.text(
            "UPDATE action_plan_measurements "
            "SET result_classification = 'not_enough_information' "
            "WHERE measurement_status = 'measured'"
        )
    )


def downgrade() -> None:
    op.drop_index(
        "ix_action_plan_measurements_result_classification",
        table_name="action_plan_measurements",
    )
    with op.batch_alter_table("action_plan_measurements") as batch_op:
        batch_op.drop_constraint(
            "ck_action_plan_measurements_result_classification",
            type_="check",
        )
    op.drop_column("action_plan_measurements", "measurement_contract")
    op.drop_column("action_plan_measurements", "result_classification")

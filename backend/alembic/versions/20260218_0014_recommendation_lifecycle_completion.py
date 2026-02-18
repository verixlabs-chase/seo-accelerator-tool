"""complete recommendation lifecycle fields and constraints

Revision ID: 20260218_0014
Revises: 20260218_0013
Create Date: 2026-02-18 22:25:00
"""
from alembic import op
import sqlalchemy as sa


revision = "20260218_0014"
down_revision = "20260218_0013"
branch_labels = None
depends_on = None


_ALLOWED_STATES = (
    "'DRAFT', 'GENERATED', 'VALIDATED', 'APPROVED', 'SCHEDULED', "
    "'EXECUTED', 'FAILED', 'ROLLED_BACK', 'ARCHIVED'"
)


def upgrade() -> None:
    with op.batch_alter_table("strategy_recommendations") as batch_op:
        batch_op.add_column(sa.Column("risk_tier", sa.Integer(), nullable=False, server_default="1"))
        batch_op.add_column(
            sa.Column("rollback_plan_json", sa.Text(), nullable=False, server_default='{"steps":[]}')
        )

    op.execute(
        "UPDATE strategy_recommendations SET status='GENERATED' "
        "WHERE status NOT IN ('DRAFT','GENERATED','VALIDATED','APPROVED','SCHEDULED','EXECUTED','FAILED','ROLLED_BACK','ARCHIVED')"
    )

    with op.batch_alter_table("strategy_recommendations") as batch_op:
        batch_op.create_check_constraint("ck_strategy_recommendations_status_values", f"status IN ({_ALLOWED_STATES})")
        batch_op.create_check_constraint("ck_strategy_recommendations_risk_tier", "risk_tier >= 0 AND risk_tier <= 4")


def downgrade() -> None:
    with op.batch_alter_table("strategy_recommendations") as batch_op:
        batch_op.drop_constraint("ck_strategy_recommendations_risk_tier", type_="check")
        batch_op.drop_constraint("ck_strategy_recommendations_status_values", type_="check")
        batch_op.drop_column("rollback_plan_json")
        batch_op.drop_column("risk_tier")

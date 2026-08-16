"""add durable automation webhook fanout and recovery

Revision ID: 20260816_0161
Revises: 20260816_0160
Create Date: 2026-08-16 20:15:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260816_0161"
down_revision = "20260816_0160"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("automation_webhook_connections") as batch_op:
        batch_op.drop_constraint(
            "ck_automation_webhook_connections_status", type_="check"
        )
        batch_op.add_column(
            sa.Column("paused_by_user_id", sa.String(length=36), nullable=True)
        )
        batch_op.add_column(
            sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_automation_webhook_connections_paused_by_user",
            "users",
            ["paused_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_check_constraint(
            "ck_automation_webhook_connections_status",
            "status in ('pending','active','unhealthy','paused','disconnected')",
        )

    with op.batch_alter_table("automation_webhook_deliveries") as batch_op:
        batch_op.drop_constraint(
            "ck_automation_webhook_deliveries_status", type_="check"
        )
        batch_op.drop_constraint(
            "ck_automation_webhook_deliveries_attempts", type_="check"
        )
        batch_op.add_column(
            sa.Column(
                "delivery_kind",
                sa.String(length=20),
                nullable=False,
                server_default="test",
            )
        )
        batch_op.add_column(
            sa.Column("source_outbox_event_id", sa.String(length=36), nullable=True)
        )
        batch_op.add_column(
            sa.Column("platform_job_id", sa.String(length=36), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "recovery_count", sa.Integer(), nullable=False, server_default="0"
            )
        )
        batch_op.add_column(
            sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("dead_lettered_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_automation_webhook_deliveries_source_outbox",
            "event_outbox",
            ["source_outbox_event_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_foreign_key(
            "fk_automation_webhook_deliveries_platform_job",
            "platform_jobs",
            ["platform_job_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_check_constraint(
            "ck_automation_webhook_deliveries_status",
            "status in ('pending','delivered','failed','dead_letter','cancelled')",
        )
        batch_op.create_check_constraint(
            "ck_automation_webhook_deliveries_attempts",
            "attempt_count >= 0 AND attempt_count <= max_attempts AND max_attempts >= 3",
        )
        batch_op.create_check_constraint(
            "ck_automation_webhook_deliveries_kind_recovery",
            "delivery_kind in ('test','product') AND recovery_count >= 0",
        )
    op.create_index(
        "ix_automation_webhook_deliveries_platform_job",
        "automation_webhook_deliveries",
        ["platform_job_id"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    recovered = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM automation_webhook_deliveries "
            "WHERE max_attempts <> 3 OR attempt_count > 3 OR recovery_count > 0"
        )
    ).scalar_one()
    if int(recovered or 0) > 0:
        raise RuntimeError(
            "Cannot downgrade automation fanout after an owner recovery without "
            "first preserving the extended attempt history in a compatible release."
        )
    bind.execute(
        sa.text(
            "UPDATE automation_webhook_deliveries SET status = 'failed' "
            "WHERE status IN ('dead_letter','cancelled')"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE automation_webhook_connections "
            "SET status = CASE WHEN verification_status = 'verified' "
            "THEN 'active' ELSE 'pending' END WHERE status = 'paused'"
        )
    )

    op.drop_index(
        "ix_automation_webhook_deliveries_platform_job",
        table_name="automation_webhook_deliveries",
    )
    with op.batch_alter_table("automation_webhook_deliveries") as batch_op:
        batch_op.drop_constraint(
            "ck_automation_webhook_deliveries_kind_recovery", type_="check"
        )
        batch_op.drop_constraint(
            "ck_automation_webhook_deliveries_attempts", type_="check"
        )
        batch_op.drop_constraint(
            "ck_automation_webhook_deliveries_status", type_="check"
        )
        batch_op.drop_constraint(
            "fk_automation_webhook_deliveries_platform_job", type_="foreignkey"
        )
        batch_op.drop_constraint(
            "fk_automation_webhook_deliveries_source_outbox", type_="foreignkey"
        )
        for column in (
            "cancelled_at",
            "dead_lettered_at",
            "next_attempt_at",
            "recovery_count",
            "platform_job_id",
            "source_outbox_event_id",
            "delivery_kind",
        ):
            batch_op.drop_column(column)
        batch_op.create_check_constraint(
            "ck_automation_webhook_deliveries_status",
            "status in ('pending','delivered','failed')",
        )
        batch_op.create_check_constraint(
            "ck_automation_webhook_deliveries_attempts",
            "attempt_count >= 0 AND attempt_count <= max_attempts AND max_attempts = 3",
        )

    with op.batch_alter_table("automation_webhook_connections") as batch_op:
        batch_op.drop_constraint(
            "ck_automation_webhook_connections_status", type_="check"
        )
        batch_op.drop_constraint(
            "fk_automation_webhook_connections_paused_by_user", type_="foreignkey"
        )
        batch_op.drop_column("paused_at")
        batch_op.drop_column("paused_by_user_id")
        batch_op.create_check_constraint(
            "ck_automation_webhook_connections_status",
            "status in ('pending','active','unhealthy','disconnected')",
        )

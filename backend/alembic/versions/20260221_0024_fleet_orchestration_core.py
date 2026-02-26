"""fleet orchestration idempotency and counters

Revision ID: 20260221_0024
Revises: 20260221_0023
Create Date: 2026-02-21 14:20:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260221_0024"
down_revision = "20260221_0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    columns = {column["name"] for column in inspector.get_columns("fleet_jobs")}
    with op.batch_alter_table("fleet_jobs") as batch_op:
        if "idempotency_key" not in columns:
            batch_op.add_column(sa.Column("idempotency_key", sa.String(length=120), nullable=True))
        if "total_items" not in columns:
            batch_op.add_column(sa.Column("total_items", sa.Integer(), nullable=False, server_default="0"))
        if "queued_items" not in columns:
            batch_op.add_column(sa.Column("queued_items", sa.Integer(), nullable=False, server_default="0"))
        if "running_items" not in columns:
            batch_op.add_column(sa.Column("running_items", sa.Integer(), nullable=False, server_default="0"))
        if "succeeded_items" not in columns:
            batch_op.add_column(sa.Column("succeeded_items", sa.Integer(), nullable=False, server_default="0"))
        if "failed_items" not in columns:
            batch_op.add_column(sa.Column("failed_items", sa.Integer(), nullable=False, server_default="0"))
        if "cancelled_items" not in columns:
            batch_op.add_column(sa.Column("cancelled_items", sa.Integer(), nullable=False, server_default="0"))

    if bind.dialect.name == "sqlite":
        op.execute("UPDATE fleet_jobs SET idempotency_key = 'legacy-' || id WHERE idempotency_key IS NULL")
    else:
        op.execute("UPDATE fleet_jobs SET idempotency_key = CONCAT('legacy-', id) WHERE idempotency_key IS NULL")

    with op.batch_alter_table("fleet_jobs") as batch_op:
        batch_op.alter_column("idempotency_key", nullable=False)

    constraints = {constraint["name"] for constraint in inspector.get_unique_constraints("fleet_jobs")}
    if "uq_fleet_jobs_portfolio_job_type_idempotency" not in constraints:
        with op.batch_alter_table("fleet_jobs") as batch_op:
            batch_op.create_unique_constraint(
                "uq_fleet_jobs_portfolio_job_type_idempotency",
                ["portfolio_id", "job_type", "idempotency_key"],
            )

    indexes = {index["name"] for index in inspector.get_indexes("fleet_jobs")}
    if "ix_fleet_jobs_portfolio_jobtype_idempotency" not in indexes:
        op.create_index(
            "ix_fleet_jobs_portfolio_jobtype_idempotency",
            "fleet_jobs",
            ["portfolio_id", "job_type", "idempotency_key"],
        )

    item_columns = {column["name"] for column in inspector.get_columns("fleet_job_items")}
    if "status" in item_columns:
        op.execute("UPDATE fleet_job_items SET status = 'queued' WHERE status = 'pending'")
        op.execute("UPDATE fleet_job_items SET status = LOWER(status) WHERE status != LOWER(status)")
    op.execute("UPDATE fleet_jobs SET status = LOWER(status) WHERE status != LOWER(status)")
    op.execute("UPDATE fleet_jobs SET job_type = LOWER(job_type) WHERE job_type != LOWER(job_type)")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    indexes = {index["name"] for index in inspector.get_indexes("fleet_jobs")}
    if "ix_fleet_jobs_portfolio_jobtype_idempotency" in indexes:
        op.drop_index("ix_fleet_jobs_portfolio_jobtype_idempotency", table_name="fleet_jobs")

    constraints = {constraint["name"] for constraint in inspector.get_unique_constraints("fleet_jobs")}
    if "uq_fleet_jobs_portfolio_job_type_idempotency" in constraints:
        with op.batch_alter_table("fleet_jobs") as batch_op:
            batch_op.drop_constraint("uq_fleet_jobs_portfolio_job_type_idempotency", type_="unique")

    columns = {column["name"] for column in inspector.get_columns("fleet_jobs")}
    with op.batch_alter_table("fleet_jobs") as batch_op:
        if "cancelled_items" in columns:
            batch_op.drop_column("cancelled_items")
        if "failed_items" in columns:
            batch_op.drop_column("failed_items")
        if "succeeded_items" in columns:
            batch_op.drop_column("succeeded_items")
        if "running_items" in columns:
            batch_op.drop_column("running_items")
        if "queued_items" in columns:
            batch_op.drop_column("queued_items")
        if "total_items" in columns:
            batch_op.drop_column("total_items")
        if "idempotency_key" in columns:
            batch_op.drop_column("idempotency_key")


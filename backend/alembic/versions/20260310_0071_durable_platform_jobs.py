"""make platform jobs durable and leaseable

Revision ID: 20260310_0071
Revises: 20260310_0070
Create Date: 2026-07-28 12:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260310_0071"
down_revision = "20260310_0070"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = [
        sa.Column("tenant_id", sa.String(length=36), nullable=True),
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default="3"),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_by", sa.String(length=128), nullable=True),
    ]
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("platform_jobs", recreate="always") as batch_op:
            for column in columns:
                batch_op.add_column(column)
    else:
        for column in columns:
            op.add_column("platform_jobs", column)

    op.create_index("ix_platform_jobs_tenant_id", "platform_jobs", ["tenant_id"], unique=False)
    op.create_index(
        "ix_platform_jobs_claimable",
        "platform_jobs",
        ["status", "available_at", "created_at"],
        unique=False,
    )
    op.create_index(
        "uq_platform_jobs_idempotency_key",
        "platform_jobs",
        ["idempotency_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_platform_jobs_idempotency_key", table_name="platform_jobs")
    op.drop_index("ix_platform_jobs_claimable", table_name="platform_jobs")
    op.drop_index("ix_platform_jobs_tenant_id", table_name="platform_jobs")
    column_names = [
        "locked_by",
        "lease_expires_at",
        "locked_at",
        "available_at",
        "max_retries",
        "idempotency_key",
        "tenant_id",
    ]
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("platform_jobs", recreate="always") as batch_op:
            for column_name in column_names:
                batch_op.drop_column(column_name)
    else:
        for column_name in column_names:
            op.drop_column("platform_jobs", column_name)

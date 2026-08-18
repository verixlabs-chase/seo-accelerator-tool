"""add governed AI provider connection validation evidence

Revision ID: 20260817_0166
Revises: 20260817_0165
Create Date: 2026-08-17 22:15:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260817_0166"
down_revision = "20260817_0165"
branch_labels = None
depends_on = None


def upgrade() -> None:
    table = "governed_ai_provider_connections"
    with op.batch_alter_table(table) as batch:
        batch.add_column(sa.Column("last_validation_latency_ms", sa.Integer(), nullable=True))
        batch.add_column(
            sa.Column("validation_schema_version", sa.String(length=60), nullable=True)
        )
        batch.add_column(
            sa.Column("validation_evidence_hash", sa.String(length=64), nullable=True)
        )
        batch.create_check_constraint(
            "ck_governed_ai_provider_connections_validation_latency",
            "last_validation_latency_ms is null OR "
            "(last_validation_latency_ms >= 0 AND last_validation_latency_ms <= 60000)",
        )


def downgrade() -> None:
    table = "governed_ai_provider_connections"
    with op.batch_alter_table(table) as batch:
        batch.drop_constraint(
            "ck_governed_ai_provider_connections_validation_latency",
            type_="check",
        )
        batch.drop_column("validation_evidence_hash")
        batch.drop_column("validation_schema_version")
        batch.drop_column("last_validation_latency_ms")

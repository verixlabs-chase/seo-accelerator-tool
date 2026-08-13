"""qualify imported directory listing evidence

Revision ID: 20260813_0140
Revises: 20260813_0139
Create Date: 2026-08-13 18:10:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260813_0140"
down_revision = "20260813_0139"
branch_labels = None
depends_on = None


def _add_provenance(table_name: str) -> None:
    op.add_column(
        table_name,
        sa.Column(
            "source_type",
            sa.String(24),
            nullable=False,
            server_default="live_collection",
        ),
    )
    op.add_column(table_name, sa.Column("source_system", sa.String(40), nullable=True))
    op.add_column(table_name, sa.Column("source_record_id", sa.String(255), nullable=True))
    op.add_column(table_name, sa.Column("source_claimed_status", sa.String(24), nullable=True))
    op.add_column(table_name, sa.Column("import_batch_id", sa.String(36), nullable=True))
    constraint_name = f"fk_{table_name}_import_batch_id"
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.create_foreign_key(
                constraint_name,
                "migration_import_batches",
                ["import_batch_id"],
                ["id"],
                ondelete="SET NULL",
            )
    else:
        op.create_foreign_key(
            constraint_name,
            table_name,
            "migration_import_batches",
            ["import_batch_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index(f"ix_{table_name}_source_type", table_name, ["source_type"])
    op.create_index(f"ix_{table_name}_import_batch_id", table_name, ["import_batch_id"])


def _drop_provenance(table_name: str) -> None:
    op.drop_index(f"ix_{table_name}_import_batch_id", table_name=table_name)
    op.drop_index(f"ix_{table_name}_source_type", table_name=table_name)
    constraint_name = f"fk_{table_name}_import_batch_id"
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.drop_constraint(constraint_name, type_="foreignkey")
    else:
        op.drop_constraint(constraint_name, table_name, type_="foreignkey")
    op.drop_column(table_name, "import_batch_id")
    op.drop_column(table_name, "source_claimed_status")
    op.drop_column(table_name, "source_record_id")
    op.drop_column(table_name, "source_system")
    op.drop_column(table_name, "source_type")


def upgrade() -> None:
    _add_provenance("directory_listings")
    _add_provenance("directory_listing_observations")


def downgrade() -> None:
    _drop_provenance("directory_listing_observations")
    _drop_provenance("directory_listings")

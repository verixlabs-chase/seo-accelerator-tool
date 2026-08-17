"""label imported ranking history with durable provenance

Revision ID: 20260813_0139
Revises: 20260813_0138
Create Date: 2026-08-13 17:15:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260813_0139"
down_revision = "20260813_0138"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ranking_snapshots",
        sa.Column(
            "source_type",
            sa.String(24),
            nullable=False,
            server_default="live_collection",
        ),
    )
    op.add_column(
        "ranking_snapshots",
        sa.Column("source_system", sa.String(40), nullable=True),
    )
    op.add_column(
        "ranking_snapshots",
        sa.Column("source_record_id", sa.String(255), nullable=True),
    )
    op.add_column(
        "ranking_snapshots",
        sa.Column("import_batch_id", sa.String(36), nullable=True),
    )
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("ranking_snapshots") as batch_op:
            batch_op.create_foreign_key(
                "fk_ranking_snapshots_import_batch_id",
                "migration_import_batches",
                ["import_batch_id"],
                ["id"],
                ondelete="SET NULL",
            )
    else:
        op.create_foreign_key(
            "fk_ranking_snapshots_import_batch_id",
            "ranking_snapshots",
            "migration_import_batches",
            ["import_batch_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index(
        "ix_ranking_snapshots_source_type",
        "ranking_snapshots",
        ["source_type"],
    )
    op.create_index(
        "ix_ranking_snapshots_import_batch_id",
        "ranking_snapshots",
        ["import_batch_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_ranking_snapshots_import_batch_id", table_name="ranking_snapshots")
    op.drop_index("ix_ranking_snapshots_source_type", table_name="ranking_snapshots")
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("ranking_snapshots") as batch_op:
            batch_op.drop_constraint(
                "fk_ranking_snapshots_import_batch_id",
                type_="foreignkey",
            )
    else:
        op.drop_constraint(
            "fk_ranking_snapshots_import_batch_id",
            "ranking_snapshots",
            type_="foreignkey",
        )
    op.drop_column("ranking_snapshots", "import_batch_id")
    op.drop_column("ranking_snapshots", "source_record_id")
    op.drop_column("ranking_snapshots", "source_system")
    op.drop_column("ranking_snapshots", "source_type")

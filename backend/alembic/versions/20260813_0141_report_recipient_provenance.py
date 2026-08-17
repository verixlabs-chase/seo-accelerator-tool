"""qualify imported report recipients

Revision ID: 20260813_0141
Revises: 20260813_0140
Create Date: 2026-08-13 19:10:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260813_0141"
down_revision = "20260813_0140"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "report_recipients",
        sa.Column("source_type", sa.String(24), nullable=False, server_default="manual"),
    )
    op.add_column(
        "report_recipients",
        sa.Column("source_system", sa.String(40), nullable=True),
    )
    op.add_column(
        "report_recipients",
        sa.Column("source_record_id", sa.String(255), nullable=True),
    )
    op.add_column(
        "report_recipients",
        sa.Column("import_batch_id", sa.String(36), nullable=True),
    )
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("report_recipients") as batch_op:
            batch_op.create_foreign_key(
                "fk_report_recipients_import_batch_id",
                "migration_import_batches",
                ["import_batch_id"],
                ["id"],
                ondelete="SET NULL",
            )
    else:
        op.create_foreign_key(
            "fk_report_recipients_import_batch_id",
            "report_recipients",
            "migration_import_batches",
            ["import_batch_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index(
        "ix_report_recipients_source_type",
        "report_recipients",
        ["source_type"],
    )
    op.create_index(
        "ix_report_recipients_import_batch_id",
        "report_recipients",
        ["import_batch_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_report_recipients_import_batch_id", table_name="report_recipients")
    op.drop_index("ix_report_recipients_source_type", table_name="report_recipients")
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("report_recipients") as batch_op:
            batch_op.drop_constraint(
                "fk_report_recipients_import_batch_id",
                type_="foreignkey",
            )
    else:
        op.drop_constraint(
            "fk_report_recipients_import_batch_id",
            "report_recipients",
            type_="foreignkey",
        )
    op.drop_column("report_recipients", "import_batch_id")
    op.drop_column("report_recipients", "source_record_id")
    op.drop_column("report_recipients", "source_system")
    op.drop_column("report_recipients", "source_type")

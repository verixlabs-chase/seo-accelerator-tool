"""store small report artifacts durably in the database

Revision ID: 20260811_0119
Revises: 20260811_0118
Create Date: 2026-08-11 20:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260811_0119"
down_revision = "20260811_0118"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("report_artifacts") as batch:
        batch.add_column(sa.Column("content_blob", sa.LargeBinary(), nullable=True))

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            sa.text(
                "GRANT SELECT, INSERT, UPDATE, DELETE "
                "ON TABLE public.report_artifacts TO lsos_app"
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("report_artifacts") as batch:
        batch.drop_column("content_blob")

"""store bounded crawl content evidence

Revision ID: 20260804_0091
Revises: 20260804_0090
Create Date: 2026-08-04 18:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260804_0091"
down_revision = "20260804_0090"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("crawl_page_results") as batch_op:
        batch_op.add_column(sa.Column("meta_description", sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column("heading_text", sa.String(length=1000), nullable=True))
        batch_op.add_column(sa.Column("body_text_excerpt", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("crawl_page_results") as batch_op:
        batch_op.drop_column("body_text_excerpt")
        batch_op.drop_column("heading_text")
        batch_op.drop_column("meta_description")

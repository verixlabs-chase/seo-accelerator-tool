"""add enterprise report logo asset

Revision ID: 20260820_0201
Revises: 20260820_0200
Create Date: 2026-08-20 10:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260820_0201"
down_revision = "20260820_0200"
branch_labels = None
depends_on = None

TABLE = "organization_report_brands"


def upgrade() -> None:
    with op.batch_alter_table(TABLE) as batch:
        batch.add_column(sa.Column("logo_content", sa.LargeBinary(), nullable=True))
        batch.add_column(sa.Column("logo_sha256", sa.String(64), nullable=True))
        batch.add_column(sa.Column("logo_width", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("logo_height", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("logo_updated_at", sa.DateTime(timezone=True), nullable=True))
        batch.create_check_constraint(
            "ck_org_report_brands_logo_complete",
            "(logo_content IS NULL AND logo_sha256 IS NULL AND logo_width IS NULL "
            "AND logo_height IS NULL AND logo_updated_at IS NULL) OR "
            "(logo_content IS NOT NULL AND logo_sha256 IS NOT NULL AND logo_width IS NOT NULL "
            "AND logo_height IS NOT NULL AND logo_updated_at IS NOT NULL)",
        )
        batch.create_check_constraint(
            "ck_org_report_brands_logo_size",
            "logo_content IS NULL OR (length(logo_content) >= 1 AND length(logo_content) <= 65536)",
        )
        batch.create_check_constraint(
            "ck_org_report_brands_logo_dimensions",
            "logo_content IS NULL OR (length(logo_sha256) = 64 "
            "AND logo_width BETWEEN 16 AND 1600 AND logo_height BETWEEN 16 AND 1600 "
            "AND logo_width * logo_height <= 1000000)",
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text(f"SELECT 1 FROM {TABLE} WHERE logo_content IS NOT NULL LIMIT 1")).first():
        raise RuntimeError(
            "Cannot downgrade while an Enterprise report logo exists. "
            "Preserve or remove it through approved maintenance first."
        )
    with op.batch_alter_table(TABLE) as batch:
        batch.drop_constraint("ck_org_report_brands_logo_dimensions", type_="check")
        batch.drop_constraint("ck_org_report_brands_logo_size", type_="check")
        batch.drop_constraint("ck_org_report_brands_logo_complete", type_="check")
        batch.drop_column("logo_updated_at")
        batch.drop_column("logo_height")
        batch.drop_column("logo_width")
        batch.drop_column("logo_sha256")
        batch.drop_column("logo_content")

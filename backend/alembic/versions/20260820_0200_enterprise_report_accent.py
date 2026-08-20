"""add enterprise report accent color

Revision ID: 20260820_0200
Revises: 20260819_0199
Create Date: 2026-08-20 09:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260820_0200"
down_revision = "20260819_0199"
branch_labels = None
depends_on = None

TABLE = "organization_report_brands"
DEFAULT_ACCENT = "#E85D19"


def upgrade() -> None:
    with op.batch_alter_table(TABLE) as batch:
        batch.add_column(
            sa.Column(
                "accent_color",
                sa.String(7),
                nullable=False,
                server_default=DEFAULT_ACCENT,
            )
        )
        batch.create_check_constraint(
            "ck_org_report_brands_accent",
            "length(accent_color) = 7 AND substr(accent_color, 1, 1) = '#'",
        )


def downgrade() -> None:
    bind = op.get_bind()
    custom = bind.execute(
        sa.text(
            f"SELECT 1 FROM {TABLE} "
            "WHERE upper(accent_color) <> :default_accent LIMIT 1"
        ),
        {"default_accent": DEFAULT_ACCENT},
    ).first()
    if custom is not None:
        raise RuntimeError(
            "Cannot downgrade while a custom Enterprise report accent exists. "
            "Preserve or reset it through approved maintenance first."
        )
    with op.batch_alter_table(TABLE) as batch:
        batch.drop_constraint("ck_org_report_brands_accent", type_="check")
        batch.drop_column("accent_color")

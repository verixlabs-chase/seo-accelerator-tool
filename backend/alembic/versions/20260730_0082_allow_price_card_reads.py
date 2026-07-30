"""allow the application role to read global provider price cards

Revision ID: 20260730_0082
Revises: 20260730_0081
Create Date: 2026-07-30 16:06:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260730_0082"
down_revision = "20260730_0081"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    op.execute(
        sa.text(
            """
            GRANT SELECT ON TABLE public.provider_price_cards TO lsos_app;
            ALTER TABLE public.provider_price_cards ENABLE ROW LEVEL SECURITY;
            DROP POLICY IF EXISTS lsos_global_read
                ON public.provider_price_cards;
            CREATE POLICY lsos_global_read
                ON public.provider_price_cards
                FOR SELECT
                TO lsos_app
                USING (true);
            """
        )
    )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    op.execute(
        sa.text(
            """
            DROP POLICY IF EXISTS lsos_global_read
                ON public.provider_price_cards;
            REVOKE SELECT ON TABLE public.provider_price_cards FROM lsos_app;
            """
        )
    )

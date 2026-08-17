"""allow the application role to read the immutable tier profile catalog

Revision ID: 20260817_0164
Revises: 20260817_0163
Create Date: 2026-08-17 14:55:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260817_0164"
down_revision = "20260817_0163"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    op.execute(
        sa.text(
            """
            GRANT SELECT ON TABLE public.tier_profiles TO lsos_app;
            ALTER TABLE public.tier_profiles ENABLE ROW LEVEL SECURITY;
            DROP POLICY IF EXISTS tier_profiles_global_read
                ON public.tier_profiles;
            CREATE POLICY tier_profiles_global_read
                ON public.tier_profiles
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
            DROP POLICY IF EXISTS tier_profiles_global_read
                ON public.tier_profiles;
            REVOKE SELECT ON TABLE public.tier_profiles FROM lsos_app;
            """
        )
    )

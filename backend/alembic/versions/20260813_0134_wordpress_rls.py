"""protect WordPress connection and inventory tables with tenant RLS

Revision ID: 20260813_0134
Revises: 20260813_0133
Create Date: 2026-08-13 03:35:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260813_0134"
down_revision = "20260813_0133"
branch_labels = None
depends_on = None


_TABLES = (
    ("wordpress_site_connections", True),
    ("wordpress_content_sync_runs", True),
    ("wordpress_content_items", True),
    ("wordpress_change_previews", False),
)


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    for table, has_organization_id in _TABLES:
        op.execute(
            sa.text(
                f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.{table} TO lsos_app"
            )
        )
        op.execute(sa.text(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY"))
        op.execute(
            sa.text(
                f"DROP POLICY IF EXISTS lsos_tenant_isolation ON public.{table}"
            )
        )
        tenant_match = (
            "tenant_id::text = current_setting('app.current_tenant_id', true)"
        )
        if has_organization_id:
            tenant_match += (
                " AND organization_id::text = "
                "current_setting('app.current_organization_id', true)"
            )
        policy_expression = (
            "current_setting('app.platform_access', true) = 'on' OR "
            f"({tenant_match})"
        )
        op.execute(
            sa.text(
                f"CREATE POLICY lsos_tenant_isolation ON public.{table} FOR ALL TO lsos_app "
                f"USING ({policy_expression}) WITH CHECK ({policy_expression})"
            )
        )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    for table, _has_organization_id in _TABLES:
        op.execute(
            sa.text(
                f"DROP POLICY IF EXISTS lsos_tenant_isolation ON public.{table}"
            )
        )
        op.execute(sa.text(f"ALTER TABLE public.{table} DISABLE ROW LEVEL SECURITY"))

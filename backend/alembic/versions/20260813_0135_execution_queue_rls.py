"""protect execution queue tables with campaign-scoped RLS

Revision ID: 20260813_0135
Revises: 20260813_0134
Create Date: 2026-08-13 04:40:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260813_0135"
down_revision = "20260813_0134"
branch_labels = None
depends_on = None


_CAMPAIGN_SCOPED_TABLES = (
    "recommendation_executions",
    "execution_mutations",
)


def _campaign_policy_expression(table: str) -> str:
    return (
        "current_setting('app.platform_access', true) = 'on' OR EXISTS ("
        "SELECT 1 FROM public.campaigns AS scoped_campaign "
        f"WHERE scoped_campaign.id = public.{table}.campaign_id "
        "AND scoped_campaign.tenant_id::text = "
        "current_setting('app.current_tenant_id', true) "
        "AND scoped_campaign.organization_id::text = "
        "current_setting('app.current_organization_id', true))"
    )


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    for table in _CAMPAIGN_SCOPED_TABLES:
        expression = _campaign_policy_expression(table)
        op.execute(
            sa.text(
                f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.{table} TO lsos_app"
            )
        )
        op.execute(sa.text(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY"))
        op.execute(
            sa.text(f"DROP POLICY IF EXISTS lsos_tenant_isolation ON public.{table}")
        )
        op.execute(
            sa.text(
                f"CREATE POLICY lsos_tenant_isolation ON public.{table} "
                f"FOR ALL TO lsos_app USING ({expression}) WITH CHECK ({expression})"
            )
        )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    for table in _CAMPAIGN_SCOPED_TABLES:
        op.execute(
            sa.text(f"DROP POLICY IF EXISTS lsos_tenant_isolation ON public.{table}")
        )
        op.execute(sa.text(f"ALTER TABLE public.{table} DISABLE ROW LEVEL SECURITY"))

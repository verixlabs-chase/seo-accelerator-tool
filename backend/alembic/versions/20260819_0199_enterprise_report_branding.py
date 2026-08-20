"""add enterprise report branding

Revision ID: 20260819_0199
Revises: 20260819_0198
Create Date: 2026-08-19 20:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260819_0199"
down_revision = "20260819_0198"
branch_labels = None
depends_on = None

TABLE = "organization_report_brands"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("brand_name", sa.String(120), nullable=False),
        sa.Column("report_title", sa.String(120), nullable=False),
        sa.Column("footer_text", sa.String(240), nullable=False),
        sa.Column("hide_platform_attribution", sa.Boolean(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_by_user_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("tenant_id = organization_id", name="ck_org_report_brands_scope"),
        sa.CheckConstraint("version >= 1", name="ck_org_report_brands_version"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", name="uq_org_report_brands_org"),
    )
    op.create_index("ix_org_report_brands_tenant", TABLE, ["tenant_id"])
    op.create_index("ix_org_report_brands_org", TABLE, ["organization_id"])
    _secure_table()


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text(f"SELECT 1 FROM {TABLE} LIMIT 1")).first() is not None:
        raise RuntimeError(
            "Cannot downgrade while Enterprise report branding exists. "
            "Preserve or remove it through approved maintenance first."
        )
    _drop_security()
    op.drop_index("ix_org_report_brands_org", table_name=TABLE)
    op.drop_index("ix_org_report_brands_tenant", table_name=TABLE)
    op.drop_table(TABLE)


def _secure_table() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    scope = (
        "current_setting('app.platform_access', true) = 'on' OR ("
        "tenant_id::text = current_setting('app.current_tenant_id', true) AND "
        "organization_id::text = current_setting('app.current_organization_id', true))"
    )
    op.execute(sa.text(f"GRANT SELECT, INSERT, UPDATE ON TABLE public.{TABLE} TO lsos_app"))
    op.execute(sa.text(f"REVOKE DELETE ON TABLE public.{TABLE} FROM lsos_app"))
    op.execute(sa.text(f"ALTER TABLE public.{TABLE} ENABLE ROW LEVEL SECURITY"))
    op.execute(
        sa.text(
            f"CREATE POLICY {TABLE}_scope ON public.{TABLE} FOR ALL TO lsos_app "
            f"USING ({scope}) WITH CHECK ({scope})"
        )
    )


def _drop_security() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(sa.text(f"DROP POLICY IF EXISTS {TABLE}_scope ON public.{TABLE}"))

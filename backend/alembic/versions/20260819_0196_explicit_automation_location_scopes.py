"""add explicit automation service account location scopes

Revision ID: 20260819_0196
Revises: 20260819_0195
Create Date: 2026-08-19 23:59:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260819_0196"
down_revision = "20260819_0195"
branch_labels = None
depends_on = None

TABLE = "automation_service_account_locations"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("service_account_id", sa.String(36), nullable=False),
        sa.Column("business_location_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["service_account_id", "tenant_id", "organization_id"],
            [
                "automation_service_accounts.id",
                "automation_service_accounts.tenant_id",
                "automation_service_accounts.organization_id",
            ],
            name="fk_automation_account_locations_account_scope",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["business_location_id", "organization_id"],
            ["business_locations.id", "business_locations.organization_id"],
            name="fk_automation_account_locations_location_scope",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "service_account_id",
            "business_location_id",
            name="uq_automation_account_locations_scope",
        ),
    )
    op.create_index(
        "ix_automation_account_locations_location",
        TABLE,
        ["organization_id", "business_location_id"],
    )
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT id, tenant_id, organization_id, business_location_id, created_at "
            "FROM automation_service_accounts"
        )
    ).mappings()
    for row in rows:
        bind.execute(
            sa.text(
                f"INSERT INTO {TABLE} "
                "(id, tenant_id, organization_id, service_account_id, business_location_id, created_at) "
                "VALUES (:id, :tenant_id, :organization_id, :account_id, :location_id, :created_at)"
            ),
            {
                "id": row["id"],
                "tenant_id": row["tenant_id"],
                "organization_id": row["organization_id"],
                "account_id": row["id"],
                "location_id": row["business_location_id"],
                "created_at": row["created_at"],
            },
        )
    if bind.dialect.name == "postgresql":
        scope = (
            "current_setting('app.platform_access', true) = 'on' OR ("
            "tenant_id::text = current_setting('app.current_tenant_id', true) AND "
            "organization_id::text = current_setting('app.current_organization_id', true))"
        )
        op.execute(
            sa.text(
                f"GRANT SELECT, INSERT, DELETE ON TABLE public.{TABLE} TO lsos_app"
            )
        )
        op.execute(sa.text(f"REVOKE UPDATE ON TABLE public.{TABLE} FROM lsos_app"))
        op.execute(sa.text(f"ALTER TABLE public.{TABLE} ENABLE ROW LEVEL SECURITY"))
        op.execute(
            sa.text(
                f"CREATE POLICY {TABLE}_scope ON public.{TABLE} FOR ALL TO lsos_app "
                f"USING ({scope}) WITH CHECK ({scope})"
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    expanded = bind.execute(
        sa.text(
            f"SELECT service_account_id FROM {TABLE} "
            "GROUP BY service_account_id HAVING COUNT(*) > 1 LIMIT 1"
        )
    ).first()
    if expanded is not None:
        raise RuntimeError(
            "Cannot downgrade while a workflow key has multiple explicit location scopes. "
            "Reduce every key to its primary location through approved maintenance first."
        )
    op.drop_index("ix_automation_account_locations_location", table_name=TABLE)
    op.drop_table(TABLE)

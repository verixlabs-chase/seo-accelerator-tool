"""add enterprise client invitations

Revision ID: 20260820_0202
Revises: 20260820_0201
Create Date: 2026-08-20 14:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260820_0202"
down_revision = "20260820_0201"
branch_labels = None
depends_on = None

TABLE = "enterprise_client_invitations"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("location_group_id", sa.String(36), nullable=False),
        sa.Column("email_hash", sa.String(64), nullable=False),
        sa.Column("encrypted_email", sa.Text(), nullable=False),
        sa.Column("encryption_key_reference", sa.String(255), nullable=False),
        sa.Column("encryption_key_version", sa.String(40), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.String(36), nullable=False),
        sa.Column("accepted_user_id", sa.String(36), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("tenant_id = organization_id", name="ck_enterprise_client_invites_scope"),
        sa.CheckConstraint(
            "status in ('active','accepted','revoked','expired')",
            name="ck_enterprise_client_invites_status",
        ),
        sa.CheckConstraint("length(email_hash) = 64", name="ck_enterprise_client_invites_email_hash"),
        sa.CheckConstraint("length(token_hash) = 64", name="ck_enterprise_client_invites_token_hash"),
        sa.CheckConstraint("version >= 1", name="ck_enterprise_client_invites_version"),
        sa.CheckConstraint("expires_at > created_at", name="ck_enterprise_client_invites_expiry"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["location_group_id", "organization_id"],
            ["portfolio_location_groups.id", "portfolio_location_groups.organization_id"],
            ondelete="RESTRICT",
            name="fk_enterprise_client_invites_group_org",
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["accepted_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_enterprise_client_invites_token_hash"),
        sa.UniqueConstraint(
            "organization_id",
            "email_hash",
            "location_group_id",
            name="uq_enterprise_client_invites_org_email_group",
        ),
    )
    op.create_index("ix_enterprise_client_invitations_tenant_id", TABLE, ["tenant_id"])
    op.create_index("ix_enterprise_client_invitations_organization_id", TABLE, ["organization_id"])
    op.create_index("ix_enterprise_client_invitations_location_group_id", TABLE, ["location_group_id"])
    op.create_index("ix_enterprise_client_invitations_token_hash", TABLE, ["token_hash"])
    op.create_index("ix_enterprise_client_invites_org_status", TABLE, ["organization_id", "status"])
    op.create_index("ix_enterprise_client_invites_expires", TABLE, ["expires_at"])
    _secure_table()


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text(f"SELECT 1 FROM {TABLE} LIMIT 1")).first() is not None:
        raise RuntimeError(
            "Cannot downgrade while Enterprise client invitations exist. "
            "Preserve or revoke them through approved maintenance first."
        )
    _drop_security()
    op.drop_index("ix_enterprise_client_invites_expires", table_name=TABLE)
    op.drop_index("ix_enterprise_client_invites_org_status", table_name=TABLE)
    op.drop_index("ix_enterprise_client_invitations_token_hash", table_name=TABLE)
    op.drop_index("ix_enterprise_client_invitations_location_group_id", table_name=TABLE)
    op.drop_index("ix_enterprise_client_invitations_organization_id", table_name=TABLE)
    op.drop_index("ix_enterprise_client_invitations_tenant_id", table_name=TABLE)
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

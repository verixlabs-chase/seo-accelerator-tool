"""organization oauth client overrides

Revision ID: 20260223_0026
Revises: 20260222_0025
Create Date: 2026-02-23 14:20:00
"""

from __future__ import annotations

from alembic import context
from alembic import op
import sqlalchemy as sa


revision = "20260223_0026"
down_revision = "20260222_0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    offline = context.is_offline_mode()
    inspector = None if offline else sa.inspect(bind)
    tables = set() if offline else set(inspector.get_table_names())

    if offline or "organization_oauth_clients" not in tables:
        op.create_table(
            "organization_oauth_clients",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column(
                "organization_id",
                sa.String(length=36),
                sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("provider_name", sa.String(length=80), nullable=False),
            sa.Column("encrypted_secret_blob", sa.Text(), nullable=False),
            sa.Column("key_reference", sa.String(length=120), nullable=False),
            sa.Column("key_version", sa.String(length=40), nullable=False, server_default="v1"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("organization_id", "provider_name", name="uq_org_oauth_clients_org_provider"),
        )

    if offline:
        op.create_index(
            "ix_organization_oauth_clients_organization_id",
            "organization_oauth_clients",
            ["organization_id"],
        )
        return

    indexes = {index["name"] for index in inspector.get_indexes("organization_oauth_clients")}
    if "ix_organization_oauth_clients_organization_id" not in indexes:
        op.create_index(
            "ix_organization_oauth_clients_organization_id",
            "organization_oauth_clients",
            ["organization_id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    offline = context.is_offline_mode()
    inspector = None if offline else sa.inspect(bind)
    tables = set() if offline else set(inspector.get_table_names())
    if not offline and "organization_oauth_clients" not in tables:
        return

    if offline:
        op.drop_index("ix_organization_oauth_clients_organization_id", table_name="organization_oauth_clients")
        op.drop_table("organization_oauth_clients")
        return

    indexes = {index["name"] for index in inspector.get_indexes("organization_oauth_clients")}
    if "ix_organization_oauth_clients_organization_id" in indexes:
        op.drop_index("ix_organization_oauth_clients_organization_id", table_name="organization_oauth_clients")
    op.drop_table("organization_oauth_clients")

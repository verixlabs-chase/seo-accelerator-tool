"""add governed AI provider candidate registry

Revision ID: 20260817_0165
Revises: 20260817_0164
Create Date: 2026-08-17 20:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260817_0165"
down_revision = "20260817_0164"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "governed_ai_provider_connections",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column(
            "adapter_type",
            sa.String(length=40),
            nullable=False,
            server_default="openai_compatible",
        ),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="candidate"),
        sa.Column("endpoint_host", sa.String(length=253), nullable=False),
        sa.Column("model_identifier", sa.String(length=200), nullable=False),
        sa.Column("capabilities_json", sa.Text(), nullable=False),
        sa.Column("encrypted_config_blob", sa.Text(), nullable=True),
        sa.Column("key_reference", sa.String(length=120), nullable=True),
        sa.Column("key_version", sa.String(length=40), nullable=True),
        sa.Column(
            "credential_configured", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "validation_status",
            sa.String(length=20),
            nullable=False,
            server_default="not_tested",
        ),
        sa.Column(
            "network_validation_status",
            sa.String(length=20),
            nullable=False,
            server_default="not_tested",
        ),
        sa.Column("last_validation_reason", sa.String(length=80), nullable=True),
        sa.Column("resolved_address_hash", sa.String(length=64), nullable=True),
        sa.Column(
            "activation_status",
            sa.String(length=20),
            nullable=False,
            server_default="inactive",
        ),
        sa.Column(
            "automatic_activation_allowed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("disconnected_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("disconnected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "adapter_type = 'openai_compatible'",
            name="ck_governed_ai_provider_connections_adapter",
        ),
        sa.CheckConstraint(
            "status in ('candidate','disconnected')",
            name="ck_governed_ai_provider_connections_status",
        ),
        sa.CheckConstraint(
            "validation_status in ('not_tested','failed','passed')",
            name="ck_governed_ai_provider_connections_validation",
        ),
        sa.CheckConstraint(
            "network_validation_status in ('not_tested','failed','passed')",
            name="ck_governed_ai_provider_connections_network_validation",
        ),
        sa.CheckConstraint(
            "activation_status = 'inactive' AND automatic_activation_allowed = false",
            name="ck_governed_ai_provider_connections_inactive",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["disconnected_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "organization_id",
            "name",
            name="uq_governed_ai_provider_connections_scope_name",
        ),
        sa.UniqueConstraint(
            "id",
            "tenant_id",
            "organization_id",
            name="uq_governed_ai_provider_connections_id_scope",
        ),
    )
    op.create_index(
        "ix_governed_ai_provider_connections_scope_status",
        "governed_ai_provider_connections",
        ["tenant_id", "organization_id", "status"],
    )

    if op.get_bind().dialect.name == "postgresql":
        table = "governed_ai_provider_connections"
        scope = (
            "current_setting('app.platform_access', true) = 'on' OR ("
            "tenant_id::text = current_setting('app.current_tenant_id', true) AND "
            "organization_id::text = current_setting('app.current_organization_id', true))"
        )
        op.execute(sa.text(f"GRANT SELECT, INSERT, UPDATE ON TABLE public.{table} TO lsos_app"))
        op.execute(sa.text(f"REVOKE DELETE ON TABLE public.{table} FROM lsos_app"))
        op.execute(sa.text(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY"))
        op.execute(
            sa.text(
                f"CREATE POLICY {table}_scope ON public.{table} "
                f"FOR ALL TO lsos_app USING ({scope}) WITH CHECK ({scope})"
            )
        )


def downgrade() -> None:
    table = "governed_ai_provider_connections"
    if op.get_bind().dialect.name == "postgresql":
        op.execute(sa.text(f"DROP POLICY IF EXISTS {table}_scope ON public.{table}"))
    op.drop_index(
        "ix_governed_ai_provider_connections_scope_status",
        table_name=table,
    )
    op.drop_table(table)

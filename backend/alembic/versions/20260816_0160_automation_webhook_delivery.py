"""add governed outbound automation webhook delivery

Revision ID: 20260816_0160
Revises: 20260815_0159
Create Date: 2026-08-16 18:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260816_0160"
down_revision = "20260815_0159"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "automation_webhook_connections",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("endpoint_host", sa.String(length=253), nullable=False),
        sa.Column("event_types_json", sa.Text(), nullable=False),
        sa.Column("encrypted_config_blob", sa.Text(), nullable=True),
        sa.Column("key_reference", sa.String(length=120), nullable=True),
        sa.Column("key_version", sa.String(length=40), nullable=True),
        sa.Column("signing_secret_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("verification_status", sa.String(length=20), nullable=False, server_default="not_tested"),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_failure_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("disconnected_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("disconnected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "provider in ('zapier','make','pipedream')",
            name="ck_automation_webhook_connections_provider",
        ),
        sa.CheckConstraint(
            "status in ('pending','active','unhealthy','disconnected')",
            name="ck_automation_webhook_connections_status",
        ),
        sa.CheckConstraint(
            "verification_status in ('not_tested','verified','failed')",
            name="ck_automation_webhook_connections_verification",
        ),
        sa.CheckConstraint(
            "signing_secret_version >= 1 AND consecutive_failures >= 0",
            name="ck_automation_webhook_connections_counters",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["disconnected_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "organization_id",
            "name",
            name="uq_automation_webhook_connections_scope_name",
        ),
        sa.UniqueConstraint(
            "id",
            "tenant_id",
            "organization_id",
            name="uq_automation_webhook_connections_id_scope",
        ),
    )
    op.create_index(
        "ix_automation_webhook_connections_scope_status",
        "automation_webhook_connections",
        ["tenant_id", "organization_id", "status"],
    )

    op.create_table(
        "automation_webhook_deliveries",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("connection_id", sa.String(length=36), nullable=False),
        sa.Column("event_id", sa.String(length=80), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("schema_version", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("encrypted_event_blob", sa.Text(), nullable=False),
        sa.Column("event_hash", sa.String(length=64), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("last_reason_code", sa.String(length=80), nullable=True),
        sa.Column("last_response_status", sa.Integer(), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status in ('pending','delivered','failed')",
            name="ck_automation_webhook_deliveries_status",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0 AND attempt_count <= max_attempts AND max_attempts = 3",
            name="ck_automation_webhook_deliveries_attempts",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["connection_id", "tenant_id", "organization_id"],
            [
                "automation_webhook_connections.id",
                "automation_webhook_connections.tenant_id",
                "automation_webhook_connections.organization_id",
            ],
            name="fk_automation_webhook_deliveries_connection_scope",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "connection_id",
            "event_id",
            name="uq_automation_webhook_deliveries_connection_event",
        ),
        sa.UniqueConstraint(
            "id",
            "tenant_id",
            "organization_id",
            name="uq_automation_webhook_deliveries_id_scope",
        ),
    )
    op.create_index(
        "ix_automation_webhook_deliveries_connection_created",
        "automation_webhook_deliveries",
        ["connection_id", "created_at"],
    )
    op.create_index(
        "ix_automation_webhook_deliveries_scope_status",
        "automation_webhook_deliveries",
        ["tenant_id", "organization_id", "status"],
    )

    op.create_table(
        "automation_webhook_delivery_attempts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("delivery_id", sa.String(length=36), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("reason_code", sa.String(length=80), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status in ('delivered','failed')",
            name="ck_automation_webhook_delivery_attempts_status",
        ),
        sa.CheckConstraint(
            "attempt_number >= 1 AND duration_ms >= 0",
            name="ck_automation_webhook_delivery_attempts_counters",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["delivery_id", "tenant_id", "organization_id"],
            [
                "automation_webhook_deliveries.id",
                "automation_webhook_deliveries.tenant_id",
                "automation_webhook_deliveries.organization_id",
            ],
            name="fk_automation_webhook_delivery_attempts_delivery_scope",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "delivery_id",
            "attempt_number",
            name="uq_automation_webhook_delivery_attempts_number",
        ),
    )
    op.create_index(
        "ix_automation_webhook_delivery_attempts_delivery",
        "automation_webhook_delivery_attempts",
        ["delivery_id", "attempted_at"],
    )

    if op.get_bind().dialect.name == "postgresql":
        scope = (
            "current_setting('app.platform_access', true) = 'on' OR ("
            "tenant_id::text = current_setting('app.current_tenant_id', true) AND "
            "organization_id::text = current_setting('app.current_organization_id', true))"
        )
        for table in (
            "automation_webhook_connections",
            "automation_webhook_deliveries",
        ):
            op.execute(sa.text(f"GRANT SELECT, INSERT, UPDATE ON TABLE public.{table} TO lsos_app"))
            op.execute(sa.text(f"REVOKE DELETE ON TABLE public.{table} FROM lsos_app"))
            op.execute(sa.text(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY"))
            op.execute(
                sa.text(
                    f"CREATE POLICY {table}_scope ON public.{table} "
                    f"FOR ALL TO lsos_app USING ({scope}) WITH CHECK ({scope})"
                )
            )
        attempt_table = "automation_webhook_delivery_attempts"
        op.execute(sa.text(f"GRANT SELECT, INSERT ON TABLE public.{attempt_table} TO lsos_app"))
        op.execute(sa.text(f"REVOKE UPDATE, DELETE ON TABLE public.{attempt_table} FROM lsos_app"))
        op.execute(sa.text(f"ALTER TABLE public.{attempt_table} ENABLE ROW LEVEL SECURITY"))
        op.execute(
            sa.text(
                f"CREATE POLICY {attempt_table}_scope ON public.{attempt_table} "
                f"FOR ALL TO lsos_app USING ({scope}) WITH CHECK ({scope})"
            )
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for table in (
            "automation_webhook_delivery_attempts",
            "automation_webhook_deliveries",
            "automation_webhook_connections",
        ):
            op.execute(sa.text(f"DROP POLICY IF EXISTS {table}_scope ON public.{table}"))
    op.drop_index(
        "ix_automation_webhook_delivery_attempts_delivery",
        table_name="automation_webhook_delivery_attempts",
    )
    op.drop_table("automation_webhook_delivery_attempts")
    op.drop_index(
        "ix_automation_webhook_deliveries_scope_status",
        table_name="automation_webhook_deliveries",
    )
    op.drop_index(
        "ix_automation_webhook_deliveries_connection_created",
        table_name="automation_webhook_deliveries",
    )
    op.drop_table("automation_webhook_deliveries")
    op.drop_index(
        "ix_automation_webhook_connections_scope_status",
        table_name="automation_webhook_connections",
    )
    op.drop_table("automation_webhook_connections")

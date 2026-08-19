"""add scoped inbound automation service accounts

Revision ID: 20260819_0188
Revises: 20260819_0187
Create Date: 2026-08-19 09:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260819_0188"
down_revision = "20260819_0187"
branch_labels = None
depends_on = None


ACCOUNT_TABLE = "automation_service_accounts"
RECEIPT_TABLE = "automation_command_receipts"


def upgrade() -> None:
    op.create_table(
        ACCOUNT_TABLE,
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("business_location_id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("token_hint", sa.String(16), nullable=False),
        sa.Column("token_version", sa.Integer(), nullable=False),
        sa.Column("allowed_commands_json", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.String(36), nullable=False),
        sa.Column("revoked_by_user_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status in ('active','revoked')",
            name="ck_automation_service_accounts_status",
        ),
        sa.CheckConstraint(
            "length(token_hash) = 64 AND token_version >= 1",
            name="ck_automation_service_accounts_token",
        ),
        sa.CheckConstraint(
            "(status = 'active' AND revoked_at IS NULL) OR "
            "(status = 'revoked' AND revoked_at IS NOT NULL)",
            name="ck_automation_service_accounts_revocation",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["business_location_id", "organization_id"],
            ["business_locations.id", "business_locations.organization_id"],
            name="fk_automation_service_accounts_location_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["revoked_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "token_hash", name="uq_automation_service_accounts_token"
        ),
        sa.UniqueConstraint(
            "id",
            "tenant_id",
            "organization_id",
            name="uq_automation_service_accounts_id_scope",
        ),
    )
    op.create_index(
        "ix_automation_service_accounts_org_status",
        ACCOUNT_TABLE,
        ["organization_id", "status", "created_at"],
    )
    op.create_index(
        "uq_automation_service_accounts_one_active_org",
        ACCOUNT_TABLE,
        ["organization_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
        sqlite_where=sa.text("status = 'active'"),
    )

    op.create_table(
        RECEIPT_TABLE,
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("service_account_id", sa.String(36), nullable=False),
        sa.Column("business_location_id", sa.String(36), nullable=False),
        sa.Column("campaign_id", sa.String(36), nullable=True),
        sa.Column("report_id", sa.String(36), nullable=False),
        sa.Column("schema_version", sa.String(80), nullable=False),
        sa.Column("command_type", sa.String(60), nullable=False),
        sa.Column("idempotency_key", sa.String(120), nullable=False),
        sa.Column("correlation_id", sa.String(120), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("denial_reason_code", sa.String(100), nullable=True),
        sa.Column("result_json", sa.Text(), nullable=False),
        sa.Column("artifact_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "command_type in ('report.retrieve')",
            name="ck_automation_command_receipts_type",
        ),
        sa.CheckConstraint(
            "status in ('succeeded','denied')",
            name="ck_automation_command_receipts_status",
        ),
        sa.CheckConstraint(
            "length(request_hash) = 64 AND length(artifact_hash) = 64",
            name="ck_automation_command_receipts_hashes",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["service_account_id", "tenant_id", "organization_id"],
            [
                "automation_service_accounts.id",
                "automation_service_accounts.tenant_id",
                "automation_service_accounts.organization_id",
            ],
            name="fk_automation_command_receipts_account_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["business_location_id", "organization_id"],
            ["business_locations.id", "business_locations.organization_id"],
            name="fk_automation_command_receipts_location_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["campaign_id", "tenant_id", "organization_id", "business_location_id"],
            [
                "campaigns.id",
                "campaigns.tenant_id",
                "campaigns.organization_id",
                "campaigns.business_location_id",
            ],
            name="fk_automation_command_receipts_campaign_scope",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "service_account_id",
            "idempotency_key",
            name="uq_automation_command_receipts_idempotency",
        ),
        sa.UniqueConstraint(
            "id",
            "tenant_id",
            "organization_id",
            name="uq_automation_command_receipts_id_scope",
        ),
    )
    op.create_index(
        "ix_automation_command_receipts_org_created",
        RECEIPT_TABLE,
        ["organization_id", "created_at"],
    )
    op.create_index(
        "ix_automation_command_receipts_account_created",
        RECEIPT_TABLE,
        ["service_account_id", "created_at"],
    )
    _secure_tables()


def downgrade() -> None:
    _drop_security()
    op.drop_index(
        "ix_automation_command_receipts_account_created", table_name=RECEIPT_TABLE
    )
    op.drop_index(
        "ix_automation_command_receipts_org_created", table_name=RECEIPT_TABLE
    )
    op.drop_table(RECEIPT_TABLE)
    op.drop_index(
        "uq_automation_service_accounts_one_active_org", table_name=ACCOUNT_TABLE
    )
    op.drop_index(
        "ix_automation_service_accounts_org_status", table_name=ACCOUNT_TABLE
    )
    op.drop_table(ACCOUNT_TABLE)


def _secure_tables() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    scope = (
        "current_setting('app.platform_access', true) = 'on' OR ("
        "tenant_id::text = current_setting('app.current_tenant_id', true) AND "
        "organization_id::text = current_setting('app.current_organization_id', true))"
    )
    op.execute(
        sa.text(
            f"GRANT SELECT, INSERT, UPDATE ON TABLE public.{ACCOUNT_TABLE} TO lsos_app"
        )
    )
    op.execute(
        sa.text(f"REVOKE DELETE ON TABLE public.{ACCOUNT_TABLE} FROM lsos_app")
    )
    op.execute(
        sa.text(f"GRANT SELECT, INSERT ON TABLE public.{RECEIPT_TABLE} TO lsos_app")
    )
    op.execute(
        sa.text(
            f"REVOKE UPDATE, DELETE ON TABLE public.{RECEIPT_TABLE} FROM lsos_app"
        )
    )
    for table in (ACCOUNT_TABLE, RECEIPT_TABLE):
        op.execute(sa.text(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY"))
        op.execute(
            sa.text(
                f"CREATE POLICY {table}_scope ON public.{table} FOR ALL TO lsos_app "
                f"USING ({scope}) WITH CHECK ({scope})"
            )
        )
    op.execute(
        sa.text(
            f"CREATE FUNCTION public.{RECEIPT_TABLE}_immutable_guard() "
            "RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN "
            "IF current_setting('app.platform_maintenance', true) = 'on' THEN "
            "RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END; END IF; "
            "RAISE EXCEPTION 'automation command receipts are immutable'; END; $$"
        )
    )
    op.execute(
        sa.text(
            f"CREATE TRIGGER {RECEIPT_TABLE}_immutable "
            f"BEFORE UPDATE OR DELETE ON public.{RECEIPT_TABLE} "
            f"FOR EACH ROW EXECUTE FUNCTION public.{RECEIPT_TABLE}_immutable_guard()"
        )
    )


def _drop_security() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(
        sa.text(
            f"DROP TRIGGER IF EXISTS {RECEIPT_TABLE}_immutable ON public.{RECEIPT_TABLE}"
        )
    )
    op.execute(
        sa.text(
            f"DROP FUNCTION IF EXISTS public.{RECEIPT_TABLE}_immutable_guard()"
        )
    )
    for table in (RECEIPT_TABLE, ACCOUNT_TABLE):
        op.execute(sa.text(f"DROP POLICY IF EXISTS {table}_scope ON public.{table}"))

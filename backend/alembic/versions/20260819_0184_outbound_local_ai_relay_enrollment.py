"""add outbound-only local AI relay enrollment

Revision ID: 20260819_0184
Revises: 20260819_0183
Create Date: 2026-08-19 05:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260819_0184"
down_revision = "20260819_0183"
branch_labels = None
depends_on = None


TABLE = "governed_ai_relay_enrollments"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("protocol_version", sa.String(60), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("token_hint", sa.String(16), nullable=False),
        sa.Column("request_id_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("customer_prompts_allowed", sa.Boolean(), nullable=False),
        sa.Column("decision_packets_enabled", sa.Boolean(), nullable=False),
        sa.Column("database_access_allowed", sa.Boolean(), nullable=False),
        sa.Column("execution_allowed", sa.Boolean(), nullable=False),
        sa.Column("publishing_allowed", sa.Boolean(), nullable=False),
        sa.Column("heartbeat_count", sa.Integer(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.String(36), nullable=True),
        sa.Column("revoked_by_user_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status in ('active','revoked')",
            name="ck_governed_ai_relay_enrollment_status",
        ),
        sa.CheckConstraint(
            "length(token_hash) = 64 AND heartbeat_count >= 0",
            name="ck_governed_ai_relay_enrollment_token_usage",
        ),
        sa.CheckConstraint(
            "customer_prompts_allowed = false "
            "AND decision_packets_enabled = false "
            "AND database_access_allowed = false "
            "AND execution_allowed = false "
            "AND publishing_allowed = false",
            name="ck_governed_ai_relay_enrollment_connection_only",
        ),
        sa.CheckConstraint(
            "(status = 'active' AND revoked_at IS NULL) OR "
            "(status = 'revoked' AND revoked_at IS NOT NULL)",
            name="ck_governed_ai_relay_enrollment_revocation",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["revoked_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "token_hash", name="uq_governed_ai_relay_enrollment_token"
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "organization_id",
            "request_id_hash",
            name="uq_governed_ai_relay_enrollment_request",
        ),
        sa.UniqueConstraint(
            "id",
            "tenant_id",
            "organization_id",
            name="uq_governed_ai_relay_enrollment_id_scope",
        ),
    )
    op.create_index(
        "ix_governed_ai_relay_enrollment_org_status",
        TABLE,
        ["organization_id", "status", "created_at"],
    )
    _secure_table()


def downgrade() -> None:
    _drop_security()
    op.drop_index("ix_governed_ai_relay_enrollment_org_status", table_name=TABLE)
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

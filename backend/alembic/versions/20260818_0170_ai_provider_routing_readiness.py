"""add append-only AI provider routing-readiness evidence

Revision ID: 20260818_0170
Revises: 20260818_0169
Create Date: 2026-08-18 17:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260818_0170"
down_revision = "20260818_0169"
branch_labels = None
depends_on = None


TABLE = "governed_ai_provider_routing_readiness"
STANDBY_TABLE = "governed_ai_provider_standby_events"


def upgrade() -> None:
    with op.batch_alter_table(STANDBY_TABLE) as batch:
        batch.create_unique_constraint(
            "uq_ai_provider_standby_events_id_scope",
            ["id", "tenant_id", "organization_id", "connection_id"],
        )

    op.create_table(
        TABLE,
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("connection_id", sa.String(36), nullable=False),
        sa.Column("standby_event_id", sa.String(36), nullable=False),
        sa.Column("readiness_version", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column(
            "managed_backend", sa.String(32), nullable=False, server_default="mistral"
        ),
        sa.Column("managed_route_status", sa.String(24), nullable=False),
        sa.Column("managed_evidence_hash", sa.String(64), nullable=True),
        sa.Column("managed_evidence_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "standby_evidence_current",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "rollback_ready", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("blockers", sa.JSON(), nullable=False),
        sa.Column(
            "usage_window_days", sa.Integer(), nullable=False, server_default="30"
        ),
        sa.Column(
            "managed_run_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "managed_validated_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "managed_fallback_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "managed_input_tokens", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "managed_output_tokens", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "candidate_run_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "traffic_percentage", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "routing_enabled", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "customer_prompts_allowed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "automatic_changes_allowed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "automatic_activation_allowed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("artifact_hash", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(64), nullable=False),
        sa.Column("created_by_user_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status in ('passed','blocked')",
            name="ck_ai_provider_readiness_status",
        ),
        sa.CheckConstraint(
            "managed_backend = 'mistral' AND "
            "managed_route_status in ('healthy','stale','unavailable','not_configured')",
            name="ck_ai_provider_readiness_managed",
        ),
        sa.CheckConstraint(
            "traffic_percentage = 0 AND routing_enabled = false AND "
            "customer_prompts_allowed = false AND automatic_changes_allowed = false "
            "AND automatic_activation_allowed = false AND candidate_run_count = 0",
            name="ck_ai_provider_readiness_no_routing",
        ),
        sa.CheckConstraint(
            "usage_window_days = 30 AND managed_run_count >= 0 AND "
            "managed_validated_count >= 0 AND managed_fallback_count >= 0 AND "
            "managed_input_tokens >= 0 AND managed_output_tokens >= 0",
            name="ck_ai_provider_readiness_usage",
        ),
        sa.CheckConstraint(
            "status != 'passed' OR (managed_route_status = 'healthy' AND "
            "standby_evidence_current = true AND rollback_ready = true)",
            name="ck_ai_provider_readiness_passed",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["connection_id", "tenant_id", "organization_id"],
            [
                "governed_ai_provider_connections.id",
                "governed_ai_provider_connections.tenant_id",
                "governed_ai_provider_connections.organization_id",
            ],
            ondelete="RESTRICT",
            name="fk_ai_provider_readiness_connection_scope",
        ),
        sa.ForeignKeyConstraint(
            ["standby_event_id", "tenant_id", "organization_id", "connection_id"],
            [
                "governed_ai_provider_standby_events.id",
                "governed_ai_provider_standby_events.tenant_id",
                "governed_ai_provider_standby_events.organization_id",
                "governed_ai_provider_standby_events.connection_id",
            ],
            ondelete="RESTRICT",
            name="fk_ai_provider_readiness_standby_scope",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "organization_id",
            "connection_id",
            "idempotency_key",
            name="uq_ai_provider_readiness_idempotency",
        ),
    )
    op.create_index(
        "ix_ai_provider_readiness_connection_created",
        TABLE,
        ["connection_id", "created_at"],
    )

    if op.get_bind().dialect.name == "postgresql":
        scope = (
            "current_setting('app.platform_access', true) = 'on' OR ("
            "tenant_id::text = current_setting('app.current_tenant_id', true) AND "
            "organization_id::text = current_setting('app.current_organization_id', true))"
        )
        op.execute(sa.text(f"GRANT SELECT, INSERT ON TABLE public.{TABLE} TO lsos_app"))
        op.execute(sa.text(f"REVOKE UPDATE, DELETE ON TABLE public.{TABLE} FROM lsos_app"))
        op.execute(sa.text(f"ALTER TABLE public.{TABLE} ENABLE ROW LEVEL SECURITY"))
        op.execute(
            sa.text(
                f"CREATE POLICY {TABLE}_scope ON public.{TABLE} "
                f"FOR ALL TO lsos_app USING ({scope}) WITH CHECK ({scope})"
            )
        )
        op.execute(
            sa.text(
                """
                CREATE OR REPLACE FUNCTION public.prevent_ai_provider_readiness_mutation()
                RETURNS trigger
                LANGUAGE plpgsql
                AS $$
                BEGIN
                    IF current_setting('app.platform_maintenance', true)
                       IS DISTINCT FROM 'on' THEN
                        RAISE EXCEPTION 'provider readiness evidence is append-only';
                    END IF;
                    IF TG_OP = 'DELETE' THEN
                        RETURN OLD;
                    END IF;
                    RETURN NEW;
                END;
                $$
                """
            )
        )
        op.execute(
            sa.text(
                f"CREATE TRIGGER trg_{TABLE}_immutable "
                f"BEFORE UPDATE OR DELETE ON public.{TABLE} "
                "FOR EACH ROW EXECUTE FUNCTION "
                "public.prevent_ai_provider_readiness_mutation()"
            )
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            sa.text(f"DROP TRIGGER IF EXISTS trg_{TABLE}_immutable ON public.{TABLE}")
        )
        op.execute(sa.text(f"DROP POLICY IF EXISTS {TABLE}_scope ON public.{TABLE}"))
        op.execute(
            sa.text("DROP FUNCTION IF EXISTS public.prevent_ai_provider_readiness_mutation()")
        )
    op.drop_index("ix_ai_provider_readiness_connection_created", table_name=TABLE)
    op.drop_table(TABLE)
    with op.batch_alter_table(STANDBY_TABLE) as batch:
        batch.drop_constraint("uq_ai_provider_standby_events_id_scope", type_="unique")

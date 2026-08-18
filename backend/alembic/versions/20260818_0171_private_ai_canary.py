"""add fixed private-AI canary routing and immutable attempt evidence

Revision ID: 20260818_0171
Revises: 20260818_0170
Create Date: 2026-08-18 19:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260818_0171"
down_revision = "20260818_0170"
branch_labels = None
depends_on = None


READINESS = "governed_ai_provider_routing_readiness"
EVENTS = "governed_ai_provider_canary_events"
ATTEMPTS = "governed_ai_provider_canary_attempts"


def upgrade() -> None:
    with op.batch_alter_table(READINESS) as batch:
        batch.create_unique_constraint(
            "uq_ai_provider_routing_readiness_id_scope",
            ["id", "tenant_id", "organization_id", "connection_id"],
        )
    op.create_table(
        EVENTS,
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("connection_id", sa.String(36), nullable=False),
        sa.Column("readiness_id", sa.String(36), nullable=False),
        sa.Column("action", sa.String(24), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("feature", sa.String(80), nullable=False),
        sa.Column("traffic_percentage", sa.Integer(), nullable=False),
        sa.Column("max_prompts_per_day", sa.Integer(), nullable=False),
        sa.Column("customer_prompts_allowed", sa.Boolean(), nullable=False),
        sa.Column("automatic_rollback_enabled", sa.Boolean(), nullable=False),
        sa.Column("automatic_changes_allowed", sa.Boolean(), nullable=False),
        sa.Column("automatic_activation_allowed", sa.Boolean(), nullable=False),
        sa.Column("readiness_artifact_hash", sa.String(64), nullable=False),
        sa.Column("acknowledgements", sa.JSON(), nullable=False),
        sa.Column("reason_code", sa.String(120), nullable=False),
        sa.Column("artifact_hash", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(64), nullable=False),
        sa.Column("created_by_user_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "action in ('enabled','disabled','automatic_rollback')",
            name="ck_ai_provider_canary_event_action",
        ),
        sa.CheckConstraint(
            "feature = 'intelligence_brief' AND max_prompts_per_day = 1",
            name="ck_ai_provider_canary_event_scope",
        ),
        sa.CheckConstraint(
            "automatic_activation_allowed = false AND automatic_changes_allowed = false",
            name="ck_ai_provider_canary_event_no_authority",
        ),
        sa.CheckConstraint(
            "(action = 'enabled' AND state = 'canary' AND traffic_percentage = 5 "
            "AND customer_prompts_allowed = true AND automatic_rollback_enabled = true) "
            "OR (action != 'enabled' AND state = 'inactive' AND traffic_percentage = 0 "
            "AND customer_prompts_allowed = false)",
            name="ck_ai_provider_canary_event_state",
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
            name="fk_ai_provider_canary_connection_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["readiness_id", "tenant_id", "organization_id", "connection_id"],
            [
                f"{READINESS}.id",
                f"{READINESS}.tenant_id",
                f"{READINESS}.organization_id",
                f"{READINESS}.connection_id",
            ],
            name="fk_ai_provider_canary_readiness_scope",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "organization_id",
            "idempotency_key",
            name="uq_ai_provider_canary_event_idempotency",
        ),
        sa.UniqueConstraint(
            "id",
            "tenant_id",
            "organization_id",
            "connection_id",
            name="uq_ai_provider_canary_event_id_scope",
        ),
    )
    op.create_index(
        "ix_ai_provider_canary_event_org_created",
        EVENTS,
        ["organization_id", "created_at"],
    )
    op.create_table(
        ATTEMPTS,
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("connection_id", sa.String(36), nullable=False),
        sa.Column("canary_event_id", sa.String(36), nullable=False),
        sa.Column("feature", sa.String(80), nullable=False),
        sa.Column("outcome", sa.String(40), nullable=False),
        sa.Column("request_key_hash", sa.String(64), nullable=False),
        sa.Column("private_error_code", sa.String(120), nullable=True),
        sa.Column("customer_prompt_sent", sa.Boolean(), nullable=False),
        sa.Column("provider_may_have_processed", sa.Boolean(), nullable=False),
        sa.Column("managed_fallback_used", sa.Boolean(), nullable=False),
        sa.Column("automatic_rollback_triggered", sa.Boolean(), nullable=False),
        sa.Column("automatic_changes_allowed", sa.Boolean(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_owner", sa.String(32), nullable=False),
        sa.Column("platform_provider_cost", sa.Integer(), nullable=False),
        sa.Column("artifact_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "outcome in ('private_succeeded','managed_fallback_succeeded',"
            "'managed_fallback_failed')",
            name="ck_ai_provider_canary_attempt_outcome",
        ),
        sa.CheckConstraint(
            "feature = 'intelligence_brief' AND customer_prompt_sent = true "
            "AND automatic_changes_allowed = false AND platform_provider_cost = 0",
            name="ck_ai_provider_canary_attempt_boundary",
        ),
        sa.CheckConstraint(
            "input_tokens >= 0 AND output_tokens >= 0",
            name="ck_ai_provider_canary_attempt_usage",
        ),
        sa.CheckConstraint(
            "(outcome = 'private_succeeded' AND managed_fallback_used = false "
            "AND automatic_rollback_triggered = false) OR "
            "(outcome != 'private_succeeded' AND managed_fallback_used = true "
            "AND automatic_rollback_triggered = true)",
            name="ck_ai_provider_canary_attempt_fallback",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["connection_id", "tenant_id", "organization_id"],
            [
                "governed_ai_provider_connections.id",
                "governed_ai_provider_connections.tenant_id",
                "governed_ai_provider_connections.organization_id",
            ],
            name="fk_ai_provider_canary_attempt_connection_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["canary_event_id", "tenant_id", "organization_id", "connection_id"],
            [
                f"{EVENTS}.id",
                f"{EVENTS}.tenant_id",
                f"{EVENTS}.organization_id",
                f"{EVENTS}.connection_id",
            ],
            name="fk_ai_provider_canary_attempt_event_scope",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "organization_id",
            "request_key_hash",
            name="uq_ai_provider_canary_attempt_request",
        ),
    )
    op.create_index(
        "ix_ai_provider_canary_attempt_org_created",
        ATTEMPTS,
        ["organization_id", "created_at"],
    )
    _secure_append_only_table(EVENTS, "provider_canary_event")
    _secure_append_only_table(ATTEMPTS, "provider_canary_attempt")


def downgrade() -> None:
    _drop_security(ATTEMPTS, "provider_canary_attempt")
    _drop_security(EVENTS, "provider_canary_event")
    op.drop_index("ix_ai_provider_canary_attempt_org_created", table_name=ATTEMPTS)
    op.drop_table(ATTEMPTS)
    op.drop_index("ix_ai_provider_canary_event_org_created", table_name=EVENTS)
    op.drop_table(EVENTS)
    with op.batch_alter_table(READINESS) as batch:
        batch.drop_constraint("uq_ai_provider_routing_readiness_id_scope", type_="unique")


def _secure_append_only_table(table: str, function_suffix: str) -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    scope = (
        "current_setting('app.platform_access', true) = 'on' OR ("
        "tenant_id::text = current_setting('app.current_tenant_id', true) AND "
        "organization_id::text = current_setting('app.current_organization_id', true))"
    )
    op.execute(sa.text(f"GRANT SELECT, INSERT ON TABLE public.{table} TO lsos_app"))
    op.execute(sa.text(f"REVOKE UPDATE, DELETE ON TABLE public.{table} FROM lsos_app"))
    op.execute(sa.text(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY"))
    op.execute(
        sa.text(
            f"CREATE POLICY {table}_scope ON public.{table} FOR ALL TO lsos_app "
            f"USING ({scope}) WITH CHECK ({scope})"
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE OR REPLACE FUNCTION public.prevent_{function_suffix}_mutation()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                IF current_setting('app.platform_maintenance', true)
                   IS DISTINCT FROM 'on' THEN
                    RAISE EXCEPTION 'private AI canary evidence is append-only';
                END IF;
                IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
                RETURN NEW;
            END;
            $$
            """
        )
    )
    op.execute(
        sa.text(
            f"CREATE TRIGGER trg_{table}_immutable BEFORE UPDATE OR DELETE "
            f"ON public.{table} FOR EACH ROW EXECUTE FUNCTION "
            f"public.prevent_{function_suffix}_mutation()"
        )
    )


def _drop_security(table: str, function_suffix: str) -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(sa.text(f"DROP TRIGGER IF EXISTS trg_{table}_immutable ON public.{table}"))
    op.execute(sa.text(f"DROP POLICY IF EXISTS {table}_scope ON public.{table}"))
    op.execute(sa.text(f"DROP FUNCTION IF EXISTS public.prevent_{function_suffix}_mutation()"))

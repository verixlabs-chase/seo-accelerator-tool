"""add governed private-AI question capability qualification and canary

Revision ID: 20260818_0173
Revises: 20260818_0172
Create Date: 2026-08-18 21:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260818_0173"
down_revision = "20260818_0172"
branch_labels = None
depends_on = None


HEALTH = "governed_ai_provider_canary_health_snapshots"
BENCHMARKS = "governed_ai_provider_capability_benchmarks"
EVENTS = "governed_ai_provider_capability_events"
ATTEMPTS = "governed_ai_provider_capability_attempts"


def upgrade() -> None:
    with op.batch_alter_table(HEALTH) as batch:
        batch.create_unique_constraint(
            "uq_ai_provider_canary_health_id_scope",
            ["id", "tenant_id", "organization_id", "connection_id"],
        )
    op.create_table(
        BENCHMARKS,
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("connection_id", sa.String(36), nullable=False),
        sa.Column("health_snapshot_id", sa.String(36), nullable=False),
        sa.Column("capability", sa.String(80), nullable=False),
        sa.Column("schema_version", sa.String(80), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("reason_code", sa.String(120), nullable=False),
        sa.Column("case_count", sa.Integer(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("customer_prompt_sent", sa.Boolean(), nullable=False),
        sa.Column("routing_enabled", sa.Boolean(), nullable=False),
        sa.Column("automatic_activation_allowed", sa.Boolean(), nullable=False),
        sa.Column("automatic_changes_allowed", sa.Boolean(), nullable=False),
        sa.Column("health_artifact_hash", sa.String(64), nullable=False),
        sa.Column("connection_evidence_hash", sa.String(64), nullable=False),
        sa.Column("artifact_hash", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(64), nullable=False),
        sa.Column("created_by_user_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "capability = 'intelligence_question' AND case_count = 1",
            name="ck_ai_provider_capability_benchmark_scope",
        ),
        sa.CheckConstraint(
            "status in ('passed','failed')",
            name="ck_ai_provider_capability_benchmark_status",
        ),
        sa.CheckConstraint(
            "latency_ms >= 0 AND latency_ms <= 60000 "
            "AND input_tokens >= 0 AND output_tokens >= 0",
            name="ck_ai_provider_capability_benchmark_metrics",
        ),
        sa.CheckConstraint(
            "customer_prompt_sent = false AND routing_enabled = false "
            "AND automatic_activation_allowed = false "
            "AND automatic_changes_allowed = false",
            name="ck_ai_provider_capability_benchmark_no_authority",
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
            name="fk_ai_provider_capability_benchmark_connection_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["health_snapshot_id", "tenant_id", "organization_id", "connection_id"],
            [
                f"{HEALTH}.id",
                f"{HEALTH}.tenant_id",
                f"{HEALTH}.organization_id",
                f"{HEALTH}.connection_id",
            ],
            name="fk_ai_provider_capability_benchmark_health_scope",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "organization_id",
            "idempotency_key",
            name="uq_ai_provider_capability_benchmark_idempotency",
        ),
        sa.UniqueConstraint(
            "id",
            "tenant_id",
            "organization_id",
            "connection_id",
            name="uq_ai_provider_capability_benchmark_id_scope",
        ),
    )
    op.create_index(
        "ix_ai_provider_capability_benchmark_org_created",
        BENCHMARKS,
        ["organization_id", "created_at"],
    )
    op.create_table(
        EVENTS,
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("connection_id", sa.String(36), nullable=False),
        sa.Column("health_snapshot_id", sa.String(36), nullable=False),
        sa.Column("benchmark_id", sa.String(36), nullable=False),
        sa.Column("action", sa.String(24), nullable=False),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("capability", sa.String(80), nullable=False),
        sa.Column("traffic_percentage", sa.Integer(), nullable=False),
        sa.Column("max_prompts_per_day", sa.Integer(), nullable=False),
        sa.Column("customer_prompts_allowed", sa.Boolean(), nullable=False),
        sa.Column("automatic_rollback_enabled", sa.Boolean(), nullable=False),
        sa.Column("automatic_activation_allowed", sa.Boolean(), nullable=False),
        sa.Column("automatic_changes_allowed", sa.Boolean(), nullable=False),
        sa.Column("acknowledgements", sa.JSON(), nullable=False),
        sa.Column("reason_code", sa.String(120), nullable=False),
        sa.Column("artifact_hash", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(64), nullable=False),
        sa.Column("created_by_user_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "action in ('enabled','disabled','automatic_rollback')",
            name="ck_ai_provider_capability_event_action",
        ),
        sa.CheckConstraint(
            "capability = 'intelligence_question' AND max_prompts_per_day = 1",
            name="ck_ai_provider_capability_event_scope",
        ),
        sa.CheckConstraint(
            "automatic_activation_allowed = false AND automatic_changes_allowed = false",
            name="ck_ai_provider_capability_event_no_authority",
        ),
        sa.CheckConstraint(
            "(action = 'enabled' AND state = 'capability_canary' "
            "AND traffic_percentage = 5 AND customer_prompts_allowed = true "
            "AND automatic_rollback_enabled = true) OR "
            "(action != 'enabled' AND state = 'inactive' "
            "AND traffic_percentage = 0 AND customer_prompts_allowed = false)",
            name="ck_ai_provider_capability_event_state",
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
            name="fk_ai_provider_capability_event_connection_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["health_snapshot_id", "tenant_id", "organization_id", "connection_id"],
            [
                f"{HEALTH}.id",
                f"{HEALTH}.tenant_id",
                f"{HEALTH}.organization_id",
                f"{HEALTH}.connection_id",
            ],
            name="fk_ai_provider_capability_event_health_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["benchmark_id", "tenant_id", "organization_id", "connection_id"],
            [
                f"{BENCHMARKS}.id",
                f"{BENCHMARKS}.tenant_id",
                f"{BENCHMARKS}.organization_id",
                f"{BENCHMARKS}.connection_id",
            ],
            name="fk_ai_provider_capability_event_benchmark_scope",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "organization_id",
            "idempotency_key",
            name="uq_ai_provider_capability_event_idempotency",
        ),
        sa.UniqueConstraint(
            "id",
            "tenant_id",
            "organization_id",
            "connection_id",
            name="uq_ai_provider_capability_event_id_scope",
        ),
    )
    op.create_index(
        "ix_ai_provider_capability_event_org_created",
        EVENTS,
        ["organization_id", "created_at"],
    )
    op.create_table(
        ATTEMPTS,
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("connection_id", sa.String(36), nullable=False),
        sa.Column("capability_event_id", sa.String(36), nullable=False),
        sa.Column("capability", sa.String(80), nullable=False),
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
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("cost_owner", sa.String(32), nullable=False),
        sa.Column("platform_provider_cost", sa.Integer(), nullable=False),
        sa.Column("artifact_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "outcome in ('private_succeeded','managed_fallback_succeeded',"
            "'managed_fallback_failed')",
            name="ck_ai_provider_capability_attempt_outcome",
        ),
        sa.CheckConstraint(
            "capability = 'intelligence_question' AND customer_prompt_sent = true "
            "AND automatic_changes_allowed = false AND platform_provider_cost = 0",
            name="ck_ai_provider_capability_attempt_scope",
        ),
        sa.CheckConstraint(
            "input_tokens >= 0 AND output_tokens >= 0 AND duration_ms >= 0 "
            "AND duration_ms <= 60000",
            name="ck_ai_provider_capability_attempt_metrics",
        ),
        sa.CheckConstraint(
            "(outcome = 'private_succeeded' AND managed_fallback_used = false "
            "AND automatic_rollback_triggered = false) OR "
            "(outcome != 'private_succeeded' AND managed_fallback_used = true "
            "AND automatic_rollback_triggered = true)",
            name="ck_ai_provider_capability_attempt_fallback",
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
            name="fk_ai_provider_capability_attempt_connection_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["capability_event_id", "tenant_id", "organization_id", "connection_id"],
            [
                f"{EVENTS}.id",
                f"{EVENTS}.tenant_id",
                f"{EVENTS}.organization_id",
                f"{EVENTS}.connection_id",
            ],
            name="fk_ai_provider_capability_attempt_event_scope",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "organization_id",
            "request_key_hash",
            name="uq_ai_provider_capability_attempt_request",
        ),
    )
    op.create_index(
        "ix_ai_provider_capability_attempt_org_created",
        ATTEMPTS,
        ["organization_id", "created_at"],
    )
    _secure(BENCHMARKS, "provider_capability_benchmark")
    _secure(EVENTS, "provider_capability_event")
    _secure(ATTEMPTS, "provider_capability_attempt")


def downgrade() -> None:
    _drop_security(ATTEMPTS, "provider_capability_attempt")
    _drop_security(EVENTS, "provider_capability_event")
    _drop_security(BENCHMARKS, "provider_capability_benchmark")
    op.drop_index("ix_ai_provider_capability_attempt_org_created", table_name=ATTEMPTS)
    op.drop_table(ATTEMPTS)
    op.drop_index("ix_ai_provider_capability_event_org_created", table_name=EVENTS)
    op.drop_table(EVENTS)
    op.drop_index("ix_ai_provider_capability_benchmark_org_created", table_name=BENCHMARKS)
    op.drop_table(BENCHMARKS)
    with op.batch_alter_table(HEALTH) as batch:
        batch.drop_constraint("uq_ai_provider_canary_health_id_scope", type_="unique")


def _secure(table: str, suffix: str) -> None:
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
            CREATE OR REPLACE FUNCTION public.prevent_{suffix}_mutation()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                IF current_setting('app.platform_maintenance', true)
                   IS DISTINCT FROM 'on' THEN
                    RAISE EXCEPTION 'private AI capability evidence is append-only';
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
            f"public.prevent_{suffix}_mutation()"
        )
    )


def _drop_security(table: str, suffix: str) -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(sa.text(f"DROP TRIGGER IF EXISTS trg_{table}_immutable ON public.{table}"))
    op.execute(sa.text(f"DROP POLICY IF EXISTS {table}_scope ON public.{table}"))
    op.execute(sa.text(f"DROP FUNCTION IF EXISTS public.prevent_{suffix}_mutation()"))

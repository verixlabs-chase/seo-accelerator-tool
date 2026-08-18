"""add immutable multi-run private-AI canary monitoring evidence

Revision ID: 20260818_0172
Revises: 20260818_0171
Create Date: 2026-08-18 20:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260818_0172"
down_revision = "20260818_0171"
branch_labels = None
depends_on = None


ATTEMPTS = "governed_ai_provider_canary_attempts"
EVENTS = "governed_ai_provider_canary_events"
HEALTH = "governed_ai_provider_canary_health_snapshots"


def upgrade() -> None:
    with op.batch_alter_table(ATTEMPTS) as batch:
        batch.drop_constraint("ck_ai_provider_canary_attempt_usage", type_="check")
        batch.add_column(
            sa.Column(
                "duration_ms",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            )
        )
        batch.create_check_constraint(
            "ck_ai_provider_canary_attempt_usage",
            "input_tokens >= 0 AND output_tokens >= 0 AND duration_ms >= 0 "
            "AND duration_ms <= 60000",
        )

    op.create_table(
        HEALTH,
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("connection_id", sa.String(36), nullable=False),
        sa.Column("canary_event_id", sa.String(36), nullable=False),
        sa.Column("feature", sa.String(80), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("window_days", sa.Integer(), nullable=False),
        sa.Column("required_success_days", sa.Integer(), nullable=False),
        sa.Column("max_latency_threshold_ms", sa.Integer(), nullable=False),
        sa.Column("private_successes", sa.Integer(), nullable=False),
        sa.Column("distinct_success_days", sa.Integer(), nullable=False),
        sa.Column("managed_fallbacks", sa.Integer(), nullable=False),
        sa.Column("automatic_rollbacks", sa.Integer(), nullable=False),
        sa.Column("max_latency_ms", sa.Integer(), nullable=False),
        sa.Column("blockers", sa.JSON(), nullable=False),
        sa.Column("traffic_change_allowed", sa.Boolean(), nullable=False),
        sa.Column("capability_change_allowed", sa.Boolean(), nullable=False),
        sa.Column("automatic_activation_allowed", sa.Boolean(), nullable=False),
        sa.Column("automatic_changes_allowed", sa.Boolean(), nullable=False),
        sa.Column("artifact_hash", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(64), nullable=False),
        sa.Column("created_by_user_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status in ('collecting','eligible_for_later_review','blocked')",
            name="ck_ai_provider_canary_health_status",
        ),
        sa.CheckConstraint(
            "feature = 'intelligence_brief' AND window_days = 30 "
            "AND required_success_days = 3 AND max_latency_threshold_ms = 8000",
            name="ck_ai_provider_canary_health_scope",
        ),
        sa.CheckConstraint(
            "private_successes >= 0 AND distinct_success_days >= 0 "
            "AND managed_fallbacks >= 0 AND automatic_rollbacks >= 0 "
            "AND max_latency_ms >= 0 AND max_latency_ms <= 60000",
            name="ck_ai_provider_canary_health_counts",
        ),
        sa.CheckConstraint(
            "traffic_change_allowed = false AND capability_change_allowed = false "
            "AND automatic_activation_allowed = false "
            "AND automatic_changes_allowed = false",
            name="ck_ai_provider_canary_health_no_authority",
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
            name="fk_ai_provider_canary_health_connection_scope",
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
            name="fk_ai_provider_canary_health_event_scope",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "organization_id",
            "idempotency_key",
            name="uq_ai_provider_canary_health_idempotency",
        ),
    )
    op.create_index(
        "ix_ai_provider_canary_health_org_created",
        HEALTH,
        ["organization_id", "created_at"],
    )
    _secure_append_only_table(HEALTH, "provider_canary_health")


def downgrade() -> None:
    _drop_security(HEALTH, "provider_canary_health")
    op.drop_index("ix_ai_provider_canary_health_org_created", table_name=HEALTH)
    op.drop_table(HEALTH)
    with op.batch_alter_table(ATTEMPTS) as batch:
        batch.drop_constraint("ck_ai_provider_canary_attempt_usage", type_="check")
        batch.drop_column("duration_ms")
        batch.create_check_constraint(
            "ck_ai_provider_canary_attempt_usage",
            "input_tokens >= 0 AND output_tokens >= 0",
        )


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
                    RAISE EXCEPTION 'private AI canary health evidence is append-only';
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

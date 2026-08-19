"""add zero-traffic governed AI provider standby events

Revision ID: 20260818_0169
Revises: 20260818_0168
Create Date: 2026-08-18 12:45:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260818_0169"
down_revision = "20260818_0168"
branch_labels = None
depends_on = None


TABLE = "governed_ai_provider_standby_events"
REVIEW_TABLE = "governed_ai_provider_reviews"


def upgrade() -> None:
    with op.batch_alter_table(REVIEW_TABLE) as batch:
        batch.create_unique_constraint(
            "uq_ai_provider_reviews_id_scope",
            ["id", "tenant_id", "organization_id", "connection_id", "benchmark_id"],
        )

    op.create_table(
        TABLE,
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("connection_id", sa.String(36), nullable=False),
        sa.Column("benchmark_id", sa.String(36), nullable=False),
        sa.Column("review_id", sa.String(36), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column(
            "managed_backend",
            sa.String(32),
            nullable=False,
            server_default="mistral",
        ),
        sa.Column(
            "routing_mode",
            sa.String(40),
            nullable=False,
            server_default="zero_traffic_standby",
        ),
        sa.Column(
            "traffic_percentage", sa.Integer(), nullable=False, server_default="0"
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
        sa.Column("benchmark_artifact_hash", sa.String(64), nullable=False),
        sa.Column("connection_evidence_hash", sa.String(64), nullable=False),
        sa.Column("review_decision_hash", sa.String(64), nullable=False),
        sa.Column("acknowledgements", sa.JSON(), nullable=False),
        sa.Column("artifact_hash", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(64), nullable=False),
        sa.Column("created_by_user_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "action in ('enabled','disabled')",
            name="ck_ai_provider_standby_events_action",
        ),
        sa.CheckConstraint(
            "managed_backend = 'mistral'",
            name="ck_ai_provider_standby_events_managed_backend",
        ),
        sa.CheckConstraint(
            "routing_mode = 'zero_traffic_standby' AND traffic_percentage = 0",
            name="ck_ai_provider_standby_events_zero_traffic",
        ),
        sa.CheckConstraint(
            "customer_prompts_allowed = false AND automatic_changes_allowed = false "
            "AND automatic_activation_allowed = false",
            name="ck_ai_provider_standby_events_no_authority",
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
            name="fk_ai_provider_standby_events_connection_scope",
        ),
        sa.ForeignKeyConstraint(
            ["benchmark_id", "tenant_id", "organization_id", "connection_id"],
            [
                "governed_ai_provider_benchmarks.id",
                "governed_ai_provider_benchmarks.tenant_id",
                "governed_ai_provider_benchmarks.organization_id",
                "governed_ai_provider_benchmarks.connection_id",
            ],
            ondelete="RESTRICT",
            name="fk_ai_provider_standby_events_benchmark_scope",
        ),
        sa.ForeignKeyConstraint(
            [
                "review_id",
                "tenant_id",
                "organization_id",
                "connection_id",
                "benchmark_id",
            ],
            [
                "governed_ai_provider_reviews.id",
                "governed_ai_provider_reviews.tenant_id",
                "governed_ai_provider_reviews.organization_id",
                "governed_ai_provider_reviews.connection_id",
                "governed_ai_provider_reviews.benchmark_id",
            ],
            ondelete="RESTRICT",
            name="fk_ai_provider_standby_events_review_scope",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "organization_id",
            "idempotency_key",
            name="uq_ai_provider_standby_events_idempotency",
        ),
    )
    op.create_index(
        "ix_ai_provider_standby_events_org_created",
        TABLE,
        ["organization_id", "created_at"],
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
                CREATE OR REPLACE FUNCTION public.prevent_ai_provider_standby_mutation()
                RETURNS trigger
                LANGUAGE plpgsql
                AS $$
                BEGIN
                    IF current_setting('app.platform_maintenance', true)
                       IS DISTINCT FROM 'on' THEN
                        RAISE EXCEPTION 'provider standby events are append-only';
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
                "public.prevent_ai_provider_standby_mutation()"
            )
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(sa.text(f"DROP TRIGGER IF EXISTS trg_{TABLE}_immutable ON public.{TABLE}"))
        op.execute(sa.text(f"DROP POLICY IF EXISTS {TABLE}_scope ON public.{TABLE}"))
        op.execute(
            sa.text("DROP FUNCTION IF EXISTS public.prevent_ai_provider_standby_mutation()")
        )
    op.drop_index("ix_ai_provider_standby_events_org_created", table_name=TABLE)
    op.drop_table(TABLE)
    with op.batch_alter_table(REVIEW_TABLE) as batch:
        batch.drop_constraint("uq_ai_provider_reviews_id_scope", type_="unique")

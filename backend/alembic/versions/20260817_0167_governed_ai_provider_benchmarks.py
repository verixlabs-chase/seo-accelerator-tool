"""add immutable governed AI provider quality benchmarks

Revision ID: 20260817_0167
Revises: 20260817_0166
Create Date: 2026-08-17 23:10:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260817_0167"
down_revision = "20260817_0166"
branch_labels = None
depends_on = None


TABLE = "governed_ai_provider_benchmarks"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("connection_id", sa.String(36), nullable=False),
        sa.Column("benchmark_version", sa.String(60), nullable=False),
        sa.Column("connection_evidence_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("case_count", sa.Integer(), nullable=False),
        sa.Column("passed_case_count", sa.Integer(), nullable=False),
        sa.Column("median_latency_ms", sa.Integer(), nullable=False),
        sa.Column("reported_input_tokens", sa.Integer(), nullable=False),
        sa.Column("reported_output_tokens", sa.Integer(), nullable=False),
        sa.Column("case_results", sa.JSON(), nullable=False),
        sa.Column("evidence_hash", sa.String(64), nullable=False),
        sa.Column("artifact_hash", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(64), nullable=False),
        sa.Column(
            "automatic_activation_allowed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("created_by_user_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status in ('passed','failed')",
            name="ck_governed_ai_provider_benchmarks_status",
        ),
        sa.CheckConstraint(
            "case_count = 3 AND passed_case_count >= 0 "
            "AND passed_case_count <= case_count",
            name="ck_governed_ai_provider_benchmarks_case_counts",
        ),
        sa.CheckConstraint(
            "median_latency_ms >= 0 AND median_latency_ms <= 60000",
            name="ck_governed_ai_provider_benchmarks_latency",
        ),
        sa.CheckConstraint(
            "reported_input_tokens >= 0 AND reported_output_tokens >= 0",
            name="ck_governed_ai_provider_benchmarks_tokens",
        ),
        sa.CheckConstraint(
            "automatic_activation_allowed = false",
            name="ck_governed_ai_provider_benchmarks_no_activation",
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
            name="fk_governed_ai_provider_benchmarks_connection_scope",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "organization_id",
            "connection_id",
            "idempotency_key",
            name="uq_governed_ai_provider_benchmarks_scope_idempotency",
        ),
        sa.UniqueConstraint(
            "id",
            "tenant_id",
            "organization_id",
            "connection_id",
            name="uq_ai_provider_benchmarks_id_scope",
        ),
    )
    op.create_index(
        "ix_governed_ai_provider_benchmarks_connection_created",
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
                CREATE OR REPLACE FUNCTION public.prevent_ai_provider_benchmark_mutation()
                RETURNS trigger
                LANGUAGE plpgsql
                AS $$
                BEGIN
                    IF current_setting('app.platform_maintenance', true)
                       IS DISTINCT FROM 'on' THEN
                        RAISE EXCEPTION 'provider benchmark artifacts are append-only';
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
                "public.prevent_ai_provider_benchmark_mutation()"
            )
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(sa.text(f"DROP TRIGGER IF EXISTS trg_{TABLE}_immutable ON public.{TABLE}"))
        op.execute(sa.text(f"DROP POLICY IF EXISTS {TABLE}_scope ON public.{TABLE}"))
        op.execute(
            sa.text(
                "DROP FUNCTION IF EXISTS public.prevent_ai_provider_benchmark_mutation()"
            )
        )
    op.drop_index(
        "ix_governed_ai_provider_benchmarks_connection_created",
        table_name=TABLE,
    )
    op.drop_table(TABLE)

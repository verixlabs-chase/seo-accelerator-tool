"""add immutable governed AI provider owner reviews

Revision ID: 20260818_0168
Revises: 20260817_0167
Create Date: 2026-08-18 09:10:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260818_0168"
down_revision = "20260817_0167"
branch_labels = None
depends_on = None


TABLE = "governed_ai_provider_reviews"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("connection_id", sa.String(36), nullable=False),
        sa.Column("benchmark_id", sa.String(36), nullable=False),
        sa.Column("decision", sa.String(40), nullable=False),
        sa.Column("benchmark_artifact_hash", sa.String(64), nullable=False),
        sa.Column("connection_evidence_hash", sa.String(64), nullable=False),
        sa.Column("acknowledgements", sa.JSON(), nullable=False),
        sa.Column("decision_hash", sa.String(64), nullable=False),
        sa.Column(
            "automatic_activation_allowed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("reviewed_by_user_id", sa.String(36), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "decision in ('approved_for_future_activation','rejected')",
            name="ck_governed_ai_provider_reviews_decision",
        ),
        sa.CheckConstraint(
            "automatic_activation_allowed = false",
            name="ck_governed_ai_provider_reviews_no_activation",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["connection_id", "tenant_id", "organization_id"],
            [
                "governed_ai_provider_connections.id",
                "governed_ai_provider_connections.tenant_id",
                "governed_ai_provider_connections.organization_id",
            ],
            ondelete="RESTRICT",
            name="fk_ai_provider_reviews_connection_scope",
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
            name="fk_ai_provider_reviews_benchmark_scope",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "organization_id",
            "benchmark_id",
            name="uq_ai_provider_reviews_benchmark",
        ),
    )
    op.create_index(
        "ix_ai_provider_reviews_connection_reviewed",
        TABLE,
        ["connection_id", "reviewed_at"],
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
                CREATE OR REPLACE FUNCTION public.prevent_ai_provider_review_mutation()
                RETURNS trigger
                LANGUAGE plpgsql
                AS $$
                BEGIN
                    IF current_setting('app.platform_maintenance', true)
                       IS DISTINCT FROM 'on' THEN
                        RAISE EXCEPTION 'provider review artifacts are append-only';
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
                "public.prevent_ai_provider_review_mutation()"
            )
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(sa.text(f"DROP TRIGGER IF EXISTS trg_{TABLE}_immutable ON public.{TABLE}"))
        op.execute(sa.text(f"DROP POLICY IF EXISTS {TABLE}_scope ON public.{TABLE}"))
        op.execute(
            sa.text("DROP FUNCTION IF EXISTS public.prevent_ai_provider_review_mutation()")
        )
    op.drop_index("ix_ai_provider_reviews_connection_reviewed", table_name=TABLE)
    op.drop_table(TABLE)

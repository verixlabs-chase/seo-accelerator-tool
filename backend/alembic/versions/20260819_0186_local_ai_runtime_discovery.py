"""add minimized local AI runtime discovery evidence

Revision ID: 20260819_0186
Revises: 20260819_0185
Create Date: 2026-08-19 07:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260819_0186"
down_revision = "20260819_0185"
branch_labels = None
depends_on = None


TABLE = "governed_ai_relay_runtime_discoveries"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("enrollment_id", sa.String(36), nullable=False),
        sa.Column("agent_version", sa.String(30), nullable=False),
        sa.Column("runtime_kind", sa.String(20), nullable=False),
        sa.Column("model_count", sa.Integer(), nullable=False),
        sa.Column("ollama_detected", sa.Boolean(), nullable=False),
        sa.Column("lm_studio_detected", sa.Boolean(), nullable=False),
        sa.Column("loopback_only", sa.Boolean(), nullable=False),
        sa.Column("customer_data_sent", sa.Boolean(), nullable=False),
        sa.Column("model_called", sa.Boolean(), nullable=False),
        sa.Column("model_identifiers_included", sa.Boolean(), nullable=False),
        sa.Column("request_signature_hash", sa.String(64), nullable=False),
        sa.Column("artifact_hash", sa.String(64), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "runtime_kind in ('not_found','ollama','lm_studio','multiple')",
            name="ck_governed_ai_relay_runtime_kind",
        ),
        sa.CheckConstraint(
            "model_count >= 0 AND model_count <= 1000 "
            "AND length(request_signature_hash) = 64 "
            "AND length(artifact_hash) = 64",
            name="ck_governed_ai_relay_runtime_counts_hashes",
        ),
        sa.CheckConstraint(
            "loopback_only = true AND customer_data_sent = false "
            "AND model_called = false AND model_identifiers_included = false",
            name="ck_governed_ai_relay_runtime_discovery_only",
        ),
        sa.CheckConstraint(
            "(runtime_kind = 'not_found' AND ollama_detected = false "
            "AND lm_studio_detected = false AND model_count = 0) OR "
            "(runtime_kind = 'ollama' AND ollama_detected = true "
            "AND lm_studio_detected = false) OR "
            "(runtime_kind = 'lm_studio' AND ollama_detected = false "
            "AND lm_studio_detected = true) OR "
            "(runtime_kind = 'multiple' AND ollama_detected = true "
            "AND lm_studio_detected = true)",
            name="ck_governed_ai_relay_runtime_detection_truth",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["enrollment_id", "tenant_id", "organization_id"],
            [
                "governed_ai_relay_enrollments.id",
                "governed_ai_relay_enrollments.tenant_id",
                "governed_ai_relay_enrollments.organization_id",
            ],
            ondelete="RESTRICT",
            name="fk_governed_ai_relay_runtime_enrollment_scope",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "id",
            "tenant_id",
            "organization_id",
            "enrollment_id",
            name="uq_governed_ai_relay_runtime_id_scope",
        ),
    )
    op.create_index(
        "ix_governed_ai_relay_runtime_enrollment_received",
        TABLE,
        ["enrollment_id", "received_at"],
    )
    op.create_index(
        "ix_governed_ai_relay_runtime_artifact_hash", TABLE, ["artifact_hash"]
    )
    _secure_append_only()


def downgrade() -> None:
    _drop_security()
    op.drop_index("ix_governed_ai_relay_runtime_artifact_hash", table_name=TABLE)
    op.drop_index(
        "ix_governed_ai_relay_runtime_enrollment_received", table_name=TABLE
    )
    op.drop_table(TABLE)


def _secure_append_only() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
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
            f"CREATE POLICY {TABLE}_scope ON public.{TABLE} FOR ALL TO lsos_app "
            f"USING ({scope}) WITH CHECK ({scope})"
        )
    )
    op.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION public.prevent_relay_runtime_mutation()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                IF current_setting('app.platform_maintenance', true)
                   IS DISTINCT FROM 'on' THEN
                    RAISE EXCEPTION 'local relay runtime evidence is append-only';
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
            f"CREATE TRIGGER trg_{TABLE}_immutable BEFORE UPDATE OR DELETE "
            f"ON public.{TABLE} FOR EACH ROW EXECUTE FUNCTION "
            "public.prevent_relay_runtime_mutation()"
        )
    )


def _drop_security() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(sa.text(f"DROP TRIGGER IF EXISTS trg_{TABLE}_immutable ON public.{TABLE}"))
    op.execute(sa.text(f"DROP POLICY IF EXISTS {TABLE}_scope ON public.{TABLE}"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS public.prevent_relay_runtime_mutation()"))

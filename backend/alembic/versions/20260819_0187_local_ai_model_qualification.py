"""add minimized synthetic local model qualification evidence

Revision ID: 20260819_0187
Revises: 20260819_0186
Create Date: 2026-08-19 08:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260819_0187"
down_revision = "20260819_0186"
branch_labels = None
depends_on = None


TABLE = "governed_ai_relay_model_qualifications"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("enrollment_id", sa.String(36), nullable=False),
        sa.Column("agent_version", sa.String(30), nullable=False),
        sa.Column("runtime_kind", sa.String(20), nullable=False),
        sa.Column("local_model_fingerprint", sa.String(64), nullable=False),
        sa.Column("prompt_version", sa.String(60), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("output_json_valid", sa.Boolean(), nullable=False),
        sa.Column("required_contract_matched", sa.Boolean(), nullable=False),
        sa.Column("synthetic_input_only", sa.Boolean(), nullable=False),
        sa.Column("model_call_attempted", sa.Boolean(), nullable=False),
        sa.Column("model_response_received", sa.Boolean(), nullable=False),
        sa.Column("customer_data_sent", sa.Boolean(), nullable=False),
        sa.Column("raw_model_identifier_sent", sa.Boolean(), nullable=False),
        sa.Column("model_output_sent", sa.Boolean(), nullable=False),
        sa.Column("customer_work_allowed", sa.Boolean(), nullable=False),
        sa.Column("publishing_allowed", sa.Boolean(), nullable=False),
        sa.Column("request_signature_hash", sa.String(64), nullable=False),
        sa.Column("artifact_hash", sa.String(64), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "runtime_kind in ('ollama','lm_studio') "
            "AND status in ('passed','failed') "
            "AND prompt_version = 'local-model-synthetic-v1'",
            name="ck_governed_ai_relay_qualification_contract",
        ),
        sa.CheckConstraint(
            "latency_ms >= 0 AND latency_ms <= 120000 "
            "AND length(local_model_fingerprint) = 64 "
            "AND length(request_signature_hash) = 64 "
            "AND length(artifact_hash) = 64",
            name="ck_governed_ai_relay_qualification_bounds",
        ),
        sa.CheckConstraint(
            "synthetic_input_only = true AND model_call_attempted = true "
            "AND customer_data_sent = false "
            "AND raw_model_identifier_sent = false "
            "AND model_output_sent = false "
            "AND customer_work_allowed = false "
            "AND publishing_allowed = false",
            name="ck_governed_ai_relay_qualification_safety",
        ),
        sa.CheckConstraint(
            "status = 'failed' OR "
            "(model_response_received = true AND output_json_valid = true "
            "AND required_contract_matched = true)",
            name="ck_governed_ai_relay_qualification_pass_truth",
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
            name="fk_governed_ai_relay_qualification_enrollment_scope",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "id",
            "tenant_id",
            "organization_id",
            "enrollment_id",
            name="uq_governed_ai_relay_qualification_id_scope",
        ),
    )
    op.create_index(
        "ix_governed_ai_relay_qualification_enrollment_received",
        TABLE,
        ["enrollment_id", "received_at"],
    )
    op.create_index(
        "ix_governed_ai_relay_qualification_fingerprint",
        TABLE,
        ["local_model_fingerprint"],
    )
    _secure_append_only()


def downgrade() -> None:
    _drop_security()
    op.drop_index(
        "ix_governed_ai_relay_qualification_fingerprint", table_name=TABLE
    )
    op.drop_index(
        "ix_governed_ai_relay_qualification_enrollment_received", table_name=TABLE
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
            CREATE OR REPLACE FUNCTION public.prevent_relay_qualification_mutation()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                IF current_setting('app.platform_maintenance', true)
                   IS DISTINCT FROM 'on' THEN
                    RAISE EXCEPTION 'local model qualification evidence is append-only';
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
            "public.prevent_relay_qualification_mutation()"
        )
    )


def _drop_security() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(sa.text(f"DROP TRIGGER IF EXISTS trg_{TABLE}_immutable ON public.{TABLE}"))
    op.execute(sa.text(f"DROP POLICY IF EXISTS {TABLE}_scope ON public.{TABLE}"))
    op.execute(
        sa.text("DROP FUNCTION IF EXISTS public.prevent_relay_qualification_mutation()")
    )

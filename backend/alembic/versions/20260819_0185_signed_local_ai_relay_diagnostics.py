"""add signed synthetic local AI relay diagnostic packets

Revision ID: 20260819_0185
Revises: 20260819_0184
Create Date: 2026-08-19 06:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260819_0185"
down_revision = "20260819_0184"
branch_labels = None
depends_on = None


PACKETS = "governed_ai_relay_diagnostic_packets"
ACKS = "governed_ai_relay_diagnostic_acknowledgements"


def upgrade() -> None:
    op.create_table(
        PACKETS,
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("enrollment_id", sa.String(36), nullable=False),
        sa.Column("protocol_version", sa.String(60), nullable=False),
        sa.Column("packet_kind", sa.String(60), nullable=False),
        sa.Column("challenge_nonce", sa.String(64), nullable=False),
        sa.Column("expected_response_hash", sa.String(64), nullable=False),
        sa.Column("artifact_hash", sa.String(64), nullable=False),
        sa.Column("request_id_hash", sa.String(64), nullable=False),
        sa.Column("customer_data_included", sa.Boolean(), nullable=False),
        sa.Column("model_execution_requested", sa.Boolean(), nullable=False),
        sa.Column("database_access_requested", sa.Boolean(), nullable=False),
        sa.Column("business_execution_requested", sa.Boolean(), nullable=False),
        sa.Column("publishing_requested", sa.Boolean(), nullable=False),
        sa.Column("created_by_user_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "packet_kind = 'synthetic_connection_challenge'",
            name="ck_governed_ai_relay_packet_kind",
        ),
        sa.CheckConstraint(
            "length(expected_response_hash) = 64 "
            "AND length(artifact_hash) = 64 "
            "AND length(request_id_hash) = 64",
            name="ck_governed_ai_relay_packet_hashes",
        ),
        sa.CheckConstraint(
            "customer_data_included = false "
            "AND model_execution_requested = false "
            "AND database_access_requested = false "
            "AND business_execution_requested = false "
            "AND publishing_requested = false",
            name="ck_governed_ai_relay_packet_synthetic_only",
        ),
        sa.CheckConstraint(
            "expires_at > created_at",
            name="ck_governed_ai_relay_packet_expiry",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["enrollment_id", "tenant_id", "organization_id"],
            [
                "governed_ai_relay_enrollments.id",
                "governed_ai_relay_enrollments.tenant_id",
                "governed_ai_relay_enrollments.organization_id",
            ],
            ondelete="RESTRICT",
            name="fk_governed_ai_relay_packet_enrollment_scope",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "organization_id",
            "enrollment_id",
            "request_id_hash",
            name="uq_governed_ai_relay_packet_request",
        ),
        sa.UniqueConstraint(
            "id",
            "tenant_id",
            "organization_id",
            "enrollment_id",
            name="uq_governed_ai_relay_packet_id_scope",
        ),
    )
    op.create_index(
        "ix_governed_ai_relay_packet_enrollment_created",
        PACKETS,
        ["enrollment_id", "created_at"],
    )
    op.create_index(
        "ix_governed_ai_relay_packet_artifact_hash",
        PACKETS,
        ["artifact_hash"],
    )
    op.create_index(
        "ix_governed_ai_relay_packet_expires_at",
        PACKETS,
        ["expires_at"],
    )

    op.create_table(
        ACKS,
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("enrollment_id", sa.String(36), nullable=False),
        sa.Column("packet_id", sa.String(36), nullable=False),
        sa.Column("response_hash", sa.String(64), nullable=False),
        sa.Column("request_signature_hash", sa.String(64), nullable=False),
        sa.Column("packet_artifact_hash", sa.String(64), nullable=False),
        sa.Column("artifact_hash", sa.String(64), nullable=False),
        sa.Column("customer_data_processed", sa.Boolean(), nullable=False),
        sa.Column("model_called", sa.Boolean(), nullable=False),
        sa.Column("database_accessed", sa.Boolean(), nullable=False),
        sa.Column("business_work_executed", sa.Boolean(), nullable=False),
        sa.Column("publishing_performed", sa.Boolean(), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "length(response_hash) = 64 "
            "AND length(request_signature_hash) = 64 "
            "AND length(packet_artifact_hash) = 64 "
            "AND length(artifact_hash) = 64",
            name="ck_governed_ai_relay_ack_hashes",
        ),
        sa.CheckConstraint(
            "customer_data_processed = false "
            "AND model_called = false "
            "AND database_accessed = false "
            "AND business_work_executed = false "
            "AND publishing_performed = false",
            name="ck_governed_ai_relay_ack_synthetic_only",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["packet_id", "tenant_id", "organization_id", "enrollment_id"],
            [
                f"{PACKETS}.id",
                f"{PACKETS}.tenant_id",
                f"{PACKETS}.organization_id",
                f"{PACKETS}.enrollment_id",
            ],
            ondelete="RESTRICT",
            name="fk_governed_ai_relay_ack_packet_scope",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("packet_id", name="uq_governed_ai_relay_ack_packet"),
        sa.UniqueConstraint(
            "id",
            "tenant_id",
            "organization_id",
            name="uq_governed_ai_relay_ack_id_scope",
        ),
    )
    op.create_index(
        "ix_governed_ai_relay_ack_enrollment_created",
        ACKS,
        ["enrollment_id", "acknowledged_at"],
    )
    op.create_index(
        "ix_governed_ai_relay_ack_artifact_hash",
        ACKS,
        ["artifact_hash"],
    )
    _secure_append_only(PACKETS, "relay_diagnostic_packets")
    _secure_append_only(ACKS, "relay_diagnostic_acks")


def downgrade() -> None:
    _drop_security(ACKS, "relay_diagnostic_acks")
    _drop_security(PACKETS, "relay_diagnostic_packets")
    op.drop_index("ix_governed_ai_relay_ack_artifact_hash", table_name=ACKS)
    op.drop_index("ix_governed_ai_relay_ack_enrollment_created", table_name=ACKS)
    op.drop_table(ACKS)
    op.drop_index("ix_governed_ai_relay_packet_expires_at", table_name=PACKETS)
    op.drop_index("ix_governed_ai_relay_packet_artifact_hash", table_name=PACKETS)
    op.drop_index("ix_governed_ai_relay_packet_enrollment_created", table_name=PACKETS)
    op.drop_table(PACKETS)


def _secure_append_only(table: str, function_suffix: str) -> None:
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
                    RAISE EXCEPTION 'local relay diagnostic evidence is append-only';
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
    op.execute(
        sa.text(f"DROP FUNCTION IF EXISTS public.prevent_{function_suffix}_mutation()")
    )

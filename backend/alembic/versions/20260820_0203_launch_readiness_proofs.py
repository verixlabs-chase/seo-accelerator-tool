"""add immutable launch readiness proofs

Revision ID: 20260820_0203
Revises: 20260820_0202
Create Date: 2026-08-20 18:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260820_0203"
down_revision = "20260820_0202"
branch_labels = None
depends_on = None

TABLE = "launch_readiness_proofs"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("schema_version", sa.String(40), nullable=False),
        sa.Column("gate_code", sa.String(50), nullable=False),
        sa.Column("result", sa.String(12), nullable=False),
        sa.Column("proof_kind", sa.String(30), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("evidence_reference", sa.String(160), nullable=False),
        sa.Column("evidence_digest", sa.String(64), nullable=False),
        sa.Column("recorded_by_user_id", sa.String(36), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "gate_code in ('critical_journeys','recovery_drills','customer_communications',"
            "'first_use_comprehension','known_limitations')",
            name="ck_launch_readiness_proofs_gate",
        ),
        sa.CheckConstraint("result in ('passed','failed')", name="ck_launch_readiness_proofs_result"),
        sa.CheckConstraint(
            "proof_kind in ('production_smoke','recovery_drill','communication_test',"
            "'moderated_test','capability_review')",
            name="ck_launch_readiness_proofs_kind",
        ),
        sa.CheckConstraint("expires_at > observed_at", name="ck_launch_readiness_proofs_expiry"),
        sa.ForeignKeyConstraint(["recorded_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("evidence_digest", name="uq_launch_readiness_proofs_digest"),
    )
    op.create_index("ix_launch_readiness_proofs_gate_code", TABLE, ["gate_code"])
    op.create_index("ix_launch_readiness_proofs_result", TABLE, ["result"])
    op.create_index("ix_launch_readiness_proofs_recorded_by", TABLE, ["recorded_by_user_id"])
    op.create_index("ix_launch_readiness_proofs_observed_at", TABLE, ["observed_at"])
    op.create_index("ix_launch_readiness_proofs_expires_at", TABLE, ["expires_at"])
    op.create_index("ix_launch_readiness_proofs_created_at", TABLE, ["created_at"])
    op.create_index(
        "ix_launch_readiness_proofs_gate_observed",
        TABLE,
        ["gate_code", "observed_at"],
    )
    _secure_table()


def downgrade() -> None:
    if op.get_bind().execute(sa.text(f"SELECT 1 FROM {TABLE} LIMIT 1")).first() is not None:
        raise RuntimeError(
            "Cannot downgrade while launch readiness proof history exists. "
            "Preserve the immutable evidence before an approved maintenance rollback."
        )
    _drop_security()
    op.drop_index("ix_launch_readiness_proofs_gate_observed", table_name=TABLE)
    op.drop_index("ix_launch_readiness_proofs_created_at", table_name=TABLE)
    op.drop_index("ix_launch_readiness_proofs_expires_at", table_name=TABLE)
    op.drop_index("ix_launch_readiness_proofs_observed_at", table_name=TABLE)
    op.drop_index("ix_launch_readiness_proofs_recorded_by", table_name=TABLE)
    op.drop_index("ix_launch_readiness_proofs_result", table_name=TABLE)
    op.drop_index("ix_launch_readiness_proofs_gate_code", table_name=TABLE)
    op.drop_table(TABLE)


def _secure_table() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(sa.text(f"GRANT SELECT, INSERT ON TABLE public.{TABLE} TO lsos_app"))
    op.execute(sa.text(f"REVOKE UPDATE, DELETE ON TABLE public.{TABLE} FROM lsos_app"))
    op.execute(sa.text(f"ALTER TABLE public.{TABLE} ENABLE ROW LEVEL SECURITY"))
    op.execute(
        sa.text(
            f"CREATE POLICY {TABLE}_select ON public.{TABLE} FOR SELECT TO lsos_app "
            "USING (current_setting('app.platform_access', true) = 'on')"
        )
    )
    op.execute(
        sa.text(
            f"CREATE POLICY {TABLE}_insert ON public.{TABLE} FOR INSERT TO lsos_app "
            "WITH CHECK (current_setting('app.platform_access', true) = 'on')"
        )
    )
    op.execute(
        sa.text(
            f"CREATE FUNCTION public.{TABLE}_immutable_guard() RETURNS trigger "
            "LANGUAGE plpgsql AS $$ BEGIN "
            "RAISE EXCEPTION 'launch readiness proofs are append-only and immutable'; END; $$"
        )
    )
    op.execute(
        sa.text(
            f"CREATE TRIGGER {TABLE}_immutable BEFORE UPDATE OR DELETE ON public.{TABLE} "
            f"FOR EACH ROW EXECUTE FUNCTION public.{TABLE}_immutable_guard()"
        )
    )


def _drop_security() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(sa.text(f"DROP TRIGGER IF EXISTS {TABLE}_immutable ON public.{TABLE}"))
    op.execute(sa.text(f"DROP FUNCTION IF EXISTS public.{TABLE}_immutable_guard()"))
    op.execute(sa.text(f"DROP POLICY IF EXISTS {TABLE}_insert ON public.{TABLE}"))
    op.execute(sa.text(f"DROP POLICY IF EXISTS {TABLE}_select ON public.{TABLE}"))

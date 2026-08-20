"""add immutable launch readiness decisions

Revision ID: 20260820_0204
Revises: 20260820_0203
Create Date: 2026-08-20 19:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260820_0204"
down_revision = "20260820_0203"
branch_labels = None
depends_on = None

TABLE = "launch_readiness_decisions"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("schema_version", sa.String(40), nullable=False),
        sa.Column("decision", sa.String(12), nullable=False),
        sa.Column("basis_digest", sa.String(64), nullable=False),
        sa.Column("release_reference", sa.String(120), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("known_limitations_acknowledged", sa.Boolean(), nullable=False),
        sa.Column("support_owner_confirmed", sa.Boolean(), nullable=False),
        sa.Column("rollback_owner_confirmed", sa.Boolean(), nullable=False),
        sa.Column("evidence_current_confirmed", sa.Boolean(), nullable=False),
        sa.Column("decision_digest", sa.String(64), nullable=False),
        sa.Column("decided_by_user_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "decision in ('go','no_go')",
            name="ck_launch_readiness_decisions_decision",
        ),
        sa.CheckConstraint(
            "length(basis_digest) = 64 and length(decision_digest) = 64",
            name="ck_launch_readiness_decisions_digests",
        ),
        sa.ForeignKeyConstraint(["decided_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("decision_digest", name="uq_launch_readiness_decisions_digest"),
    )
    op.create_index("ix_launch_readiness_decisions_decision", TABLE, ["decision"])
    op.create_index("ix_launch_readiness_decisions_basis_digest", TABLE, ["basis_digest"])
    op.create_index("ix_launch_readiness_decisions_decided_by", TABLE, ["decided_by_user_id"])
    op.create_index("ix_launch_readiness_decisions_created", TABLE, ["created_at"])
    _secure_table()


def downgrade() -> None:
    if op.get_bind().execute(sa.text(f"SELECT 1 FROM {TABLE} LIMIT 1")).first() is not None:
        raise RuntimeError(
            "Cannot downgrade while launch decision history exists. "
            "Preserve the immutable decision before an approved maintenance rollback."
        )
    _drop_security()
    op.drop_index("ix_launch_readiness_decisions_created", table_name=TABLE)
    op.drop_index("ix_launch_readiness_decisions_decided_by", table_name=TABLE)
    op.drop_index("ix_launch_readiness_decisions_basis_digest", table_name=TABLE)
    op.drop_index("ix_launch_readiness_decisions_decision", table_name=TABLE)
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
            "RAISE EXCEPTION 'launch readiness decisions are append-only and immutable'; END; $$"
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

"""add immutable launch experience reviews

Revision ID: 20260820_0207
Revises: 20260820_0206
Create Date: 2026-08-20 22:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260820_0207"
down_revision = "20260820_0206"
branch_labels = None
depends_on = None

TABLE = "launch_experience_reviews"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("schema_version", sa.String(40), nullable=False),
        sa.Column("review_kind", sa.String(24), nullable=False),
        sa.Column("subject_code", sa.String(64), nullable=False),
        sa.Column("viewport", sa.String(20), nullable=False),
        sa.Column("result", sa.String(16), nullable=False),
        sa.Column("session_reference", sa.String(40), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("issue_count", sa.Integer(), nullable=False),
        sa.Column("blocking_issue_count", sa.Integer(), nullable=False),
        sa.Column("evidence_reference", sa.String(160), nullable=False),
        sa.Column("evidence_digest", sa.String(64), nullable=False),
        sa.Column("recorded_by_user_id", sa.String(36), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "review_kind in ('route_audit','moderated_session')",
            name="ck_launch_experience_reviews_kind",
        ),
        sa.CheckConstraint(
            "viewport in ('desktop','mobile','not_applicable')",
            name="ck_launch_experience_reviews_viewport",
        ),
        sa.CheckConstraint(
            "result in ('passed','failed')",
            name="ck_launch_experience_reviews_result",
        ),
        sa.CheckConstraint(
            "issue_count >= 0 and blocking_issue_count >= 0 "
            "and blocking_issue_count <= issue_count",
            name="ck_launch_experience_reviews_issue_counts",
        ),
        sa.CheckConstraint(
            "result <> 'passed' or blocking_issue_count = 0",
            name="ck_launch_experience_reviews_passed_clear",
        ),
        sa.CheckConstraint(
            "expires_at > observed_at",
            name="ck_launch_experience_reviews_expiry",
        ),
        sa.ForeignKeyConstraint(
            ["recorded_by_user_id"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "evidence_digest",
            name="uq_launch_experience_reviews_digest",
        ),
    )
    for column in (
        "review_kind",
        "subject_code",
        "viewport",
        "result",
        "session_reference",
        "recorded_by_user_id",
        "observed_at",
        "expires_at",
        "created_at",
    ):
        op.create_index(f"ix_{TABLE}_{column}", TABLE, [column])
    op.create_index(
        "ix_launch_experience_subject_view_observed",
        TABLE,
        ["subject_code", "viewport", "observed_at"],
    )
    _secure_table()


def downgrade() -> None:
    if op.get_bind().execute(sa.text(f"SELECT 1 FROM {TABLE} LIMIT 1")).first() is not None:
        raise RuntimeError(
            "Cannot downgrade while launch experience review history exists. "
            "Preserve the immutable reviews before an approved maintenance rollback."
        )
    _drop_security()
    op.drop_index("ix_launch_experience_subject_view_observed", table_name=TABLE)
    for column in reversed(
        (
            "review_kind",
            "subject_code",
            "viewport",
            "result",
            "session_reference",
            "recorded_by_user_id",
            "observed_at",
            "expires_at",
            "created_at",
        )
    ):
        op.drop_index(f"ix_{TABLE}_{column}", table_name=TABLE)
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
            "RAISE EXCEPTION 'launch experience reviews are append-only and immutable'; END; $$"
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

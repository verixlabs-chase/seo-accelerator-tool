"""add immutable customer status updates

Revision ID: 20260820_0205
Revises: 20260820_0204
Create Date: 2026-08-20 20:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260820_0205"
down_revision = "20260820_0204"
branch_labels = None
depends_on = None

TABLE = "customer_status_updates"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("schema_version", sa.String(40), nullable=False),
        sa.Column("incident_key", sa.String(64), nullable=False),
        sa.Column("update_number", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("impact", sa.String(12), nullable=False),
        sa.Column("title", sa.String(100), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("affected_surfaces", sa.JSON(), nullable=False),
        sa.Column("visible_to_customers", sa.Boolean(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("content_digest", sa.String(64), nullable=False),
        sa.Column("created_by_user_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "state in ('investigating','identified','monitoring','resolved','maintenance')",
            name="ck_customer_status_updates_state",
        ),
        sa.CheckConstraint(
            "impact in ('none','minor','major','critical')",
            name="ck_customer_status_updates_impact",
        ),
        sa.CheckConstraint("update_number > 0", name="ck_customer_status_updates_number"),
        sa.CheckConstraint(
            "ends_at is null or ends_at > starts_at",
            name="ck_customer_status_updates_window",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "incident_key",
            "update_number",
            name="uq_customer_status_updates_incident_number",
        ),
        sa.UniqueConstraint("content_digest", name="uq_customer_status_updates_digest"),
    )
    op.create_index("ix_customer_status_updates_incident_key", TABLE, ["incident_key"])
    op.create_index("ix_customer_status_updates_state", TABLE, ["state"])
    op.create_index("ix_customer_status_updates_impact", TABLE, ["impact"])
    op.create_index(
        "ix_customer_status_updates_created_by_user_id",
        TABLE,
        ["created_by_user_id"],
    )
    op.create_index("ix_customer_status_updates_created_at", TABLE, ["created_at"])
    op.create_index(
        "ix_customer_status_updates_incident_created",
        TABLE,
        ["incident_key", "created_at"],
    )
    op.create_index(
        "ix_customer_status_updates_visible_created",
        TABLE,
        ["visible_to_customers", "created_at"],
    )
    _secure_table()


def downgrade() -> None:
    if op.get_bind().execute(sa.text(f"SELECT 1 FROM {TABLE} LIMIT 1")).first() is not None:
        raise RuntimeError(
            "Cannot downgrade while customer status history exists. "
            "Preserve the immutable incident record before an approved maintenance rollback."
        )
    _drop_security()
    op.drop_index("ix_customer_status_updates_visible_created", table_name=TABLE)
    op.drop_index("ix_customer_status_updates_incident_created", table_name=TABLE)
    op.drop_index("ix_customer_status_updates_created_at", table_name=TABLE)
    op.drop_index("ix_customer_status_updates_created_by_user_id", table_name=TABLE)
    op.drop_index("ix_customer_status_updates_impact", table_name=TABLE)
    op.drop_index("ix_customer_status_updates_state", table_name=TABLE)
    op.drop_index("ix_customer_status_updates_incident_key", table_name=TABLE)
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
            "USING (visible_to_customers OR "
            "current_setting('app.platform_access', true) = 'on')"
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
            "RAISE EXCEPTION 'customer status updates are append-only and immutable'; END; $$"
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

"""add tenant-scoped in-product notification center

Revision ID: 20260822_0210
Revises: 20260822_0209
Create Date: 2026-08-22 12:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260822_0210"
down_revision = "20260822_0209"
branch_labels = None
depends_on = None

NOTIFICATIONS_TABLE = "notifications"
USER_STATES_TABLE = "notification_user_states"


def upgrade() -> None:
    op.create_table(
        NOTIFICATIONS_TABLE,
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("schema_version", sa.String(40), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("location_id", sa.String(36), nullable=True),
        sa.Column("organization_name", sa.String(255), nullable=False),
        sa.Column("location_name", sa.String(255), nullable=True),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("severity", sa.String(24), nullable=False),
        sa.Column("source_event_id", sa.String(36), nullable=False),
        sa.Column("source_event_type", sa.String(120), nullable=False),
        sa.Column("source_label", sa.String(80), nullable=False),
        sa.Column("resource_type", sa.String(40), nullable=False),
        sa.Column("resource_id", sa.String(80), nullable=False),
        sa.Column("title", sa.String(180), nullable=False),
        sa.Column("meaning", sa.Text(), nullable=False),
        sa.Column("action_label", sa.String(120), nullable=False),
        sa.Column("action_url", sa.String(500), nullable=False),
        sa.Column("freshness_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("semantic_fingerprint", sa.String(64), nullable=False),
        sa.Column("cooldown_window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cooldown_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("tenant_id = organization_id", name="ck_notifications_scope"),
        sa.CheckConstraint(
            "event_type in ('report.ready','action.failed')",
            name="ck_notifications_event_type",
        ),
        sa.CheckConstraint(
            "severity in ('information','needs_attention')",
            name="ck_notifications_severity",
        ),
        sa.CheckConstraint(
            "length(semantic_fingerprint) = 64",
            name="ck_notifications_semantic_fingerprint",
        ),
        sa.CheckConstraint(
            "cooldown_expires_at > cooldown_window_started_at",
            name="ck_notifications_cooldown_window",
        ),
        sa.CheckConstraint(
            "action_url like '/%' and action_url not like '//%'",
            name="ck_notifications_action_url",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["location_id", "organization_id"],
            ["business_locations.id", "business_locations.organization_id"],
            ondelete="RESTRICT",
            name="fk_notifications_location_org",
        ),
        sa.ForeignKeyConstraint(
            ["source_event_id"],
            ["event_outbox.id"],
            ondelete="RESTRICT",
            name="fk_notifications_source_event",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "id",
            "tenant_id",
            "organization_id",
            name="uq_notifications_scoped_identity",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "source_event_id",
            name="uq_notifications_source_event",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "semantic_fingerprint",
            "cooldown_window_started_at",
            name="uq_notifications_semantic_cooldown",
        ),
    )
    for column in (
        "tenant_id",
        "organization_id",
        "location_id",
        "event_type",
        "severity",
        "source_event_id",
    ):
        op.create_index(
            f"ix_{NOTIFICATIONS_TABLE}_{column}",
            NOTIFICATIONS_TABLE,
            [column],
        )
    op.create_index(
        "ix_notifications_org_observed",
        NOTIFICATIONS_TABLE,
        ["organization_id", "observed_at"],
    )
    op.create_index(
        "ix_notifications_org_location_observed",
        NOTIFICATIONS_TABLE,
        ["organization_id", "location_id", "observed_at"],
    )

    op.create_table(
        USER_STATES_TABLE,
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("notification_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "tenant_id = organization_id",
            name="ck_notification_user_states_scope",
        ),
        sa.CheckConstraint(
            "read_at is not null or dismissed_at is not null",
            name="ck_notification_user_states_has_state",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["notification_id", "tenant_id", "organization_id"],
            ["notifications.id", "notifications.tenant_id", "notifications.organization_id"],
            ondelete="CASCADE",
            name="fk_notification_user_states_notification_scope",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "notification_id",
            "user_id",
            name="uq_notification_user_states_notification_user",
        ),
    )
    for column in ("tenant_id", "organization_id", "notification_id", "user_id"):
        op.create_index(
            f"ix_{USER_STATES_TABLE}_{column}",
            USER_STATES_TABLE,
            [column],
        )
    op.create_index(
        "ix_notification_user_states_user_state",
        USER_STATES_TABLE,
        ["organization_id", "user_id", "dismissed_at", "read_at"],
    )
    _secure_tables()


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text(f"SELECT 1 FROM {USER_STATES_TABLE} LIMIT 1")).first() is not None:
        raise RuntimeError(
            "Cannot downgrade while notification member state exists. "
            "Preserve the read and dismissal history before approved maintenance."
        )
    if bind.execute(sa.text(f"SELECT 1 FROM {NOTIFICATIONS_TABLE} LIMIT 1")).first() is not None:
        raise RuntimeError(
            "Cannot downgrade while notifications exist. "
            "Preserve the durable notification history before approved maintenance."
        )
    _drop_security()
    op.drop_index(
        "ix_notification_user_states_user_state",
        table_name=USER_STATES_TABLE,
    )
    for column in reversed(("tenant_id", "organization_id", "notification_id", "user_id")):
        op.drop_index(
            f"ix_{USER_STATES_TABLE}_{column}",
            table_name=USER_STATES_TABLE,
        )
    op.drop_table(USER_STATES_TABLE)
    op.drop_index(
        "ix_notifications_org_location_observed",
        table_name=NOTIFICATIONS_TABLE,
    )
    op.drop_index("ix_notifications_org_observed", table_name=NOTIFICATIONS_TABLE)
    for column in reversed(
        (
            "tenant_id",
            "organization_id",
            "location_id",
            "event_type",
            "severity",
            "source_event_id",
        )
    ):
        op.drop_index(
            f"ix_{NOTIFICATIONS_TABLE}_{column}",
            table_name=NOTIFICATIONS_TABLE,
        )
    op.drop_table(NOTIFICATIONS_TABLE)


def _secure_tables() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    tenant_scope = (
        "current_setting('app.platform_access', true) = 'on' OR ("
        "tenant_id::text = current_setting('app.current_tenant_id', true) AND "
        "organization_id::text = current_setting('app.current_organization_id', true))"
    )
    user_scope = (
        "current_setting('app.platform_access', true) = 'on' OR ("
        "tenant_id::text = current_setting('app.current_tenant_id', true) AND "
        "organization_id::text = current_setting('app.current_organization_id', true) AND "
        "user_id::text = current_setting('app.current_user_id', true))"
    )

    op.execute(
        sa.text(
            f"GRANT SELECT, INSERT ON TABLE public.{NOTIFICATIONS_TABLE} TO lsos_app"
        )
    )
    op.execute(
        sa.text(
            f"REVOKE UPDATE, DELETE ON TABLE public.{NOTIFICATIONS_TABLE} FROM lsos_app"
        )
    )
    op.execute(
        sa.text(f"ALTER TABLE public.{NOTIFICATIONS_TABLE} ENABLE ROW LEVEL SECURITY")
    )
    op.execute(
        sa.text(
            f"CREATE POLICY {NOTIFICATIONS_TABLE}_select ON public.{NOTIFICATIONS_TABLE} "
            f"FOR SELECT TO lsos_app USING ({tenant_scope})"
        )
    )
    op.execute(
        sa.text(
            f"CREATE POLICY {NOTIFICATIONS_TABLE}_insert ON public.{NOTIFICATIONS_TABLE} "
            f"FOR INSERT TO lsos_app WITH CHECK ({tenant_scope})"
        )
    )
    op.execute(
        sa.text(
            f"CREATE FUNCTION public.{NOTIFICATIONS_TABLE}_immutable_guard() RETURNS trigger "
            "LANGUAGE plpgsql AS $$ BEGIN "
            "RAISE EXCEPTION 'notifications are immutable'; END; $$"
        )
    )
    op.execute(
        sa.text(
            f"CREATE TRIGGER {NOTIFICATIONS_TABLE}_immutable BEFORE UPDATE OR DELETE "
            f"ON public.{NOTIFICATIONS_TABLE} FOR EACH ROW EXECUTE FUNCTION "
            f"public.{NOTIFICATIONS_TABLE}_immutable_guard()"
        )
    )

    op.execute(
        sa.text(
            f"GRANT SELECT, INSERT ON TABLE public.{USER_STATES_TABLE} TO lsos_app"
        )
    )
    op.execute(
        sa.text(
            f"REVOKE UPDATE, DELETE ON TABLE public.{USER_STATES_TABLE} FROM lsos_app"
        )
    )
    op.execute(
        sa.text(
            f"GRANT UPDATE (read_at, dismissed_at, updated_at) "
            f"ON TABLE public.{USER_STATES_TABLE} TO lsos_app"
        )
    )
    op.execute(
        sa.text(f"ALTER TABLE public.{USER_STATES_TABLE} ENABLE ROW LEVEL SECURITY")
    )
    op.execute(
        sa.text(
            f"CREATE POLICY {USER_STATES_TABLE}_scope ON public.{USER_STATES_TABLE} "
            f"FOR ALL TO lsos_app USING ({user_scope}) WITH CHECK ({user_scope})"
        )
    )
    op.execute(
        sa.text(
            f"CREATE FUNCTION public.{USER_STATES_TABLE}_transition_guard() RETURNS trigger "
            "LANGUAGE plpgsql AS $$ BEGIN "
            "IF NEW.id IS DISTINCT FROM OLD.id "
            "OR NEW.tenant_id IS DISTINCT FROM OLD.tenant_id "
            "OR NEW.organization_id IS DISTINCT FROM OLD.organization_id "
            "OR NEW.notification_id IS DISTINCT FROM OLD.notification_id "
            "OR NEW.user_id IS DISTINCT FROM OLD.user_id "
            "OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN "
            "RAISE EXCEPTION 'notification member state identity is immutable'; "
            "END IF; "
            "IF (OLD.read_at IS NOT NULL AND NEW.read_at IS DISTINCT FROM OLD.read_at) "
            "OR (OLD.dismissed_at IS NOT NULL "
            "AND NEW.dismissed_at IS DISTINCT FROM OLD.dismissed_at) THEN "
            "RAISE EXCEPTION 'notification member state cannot be cleared or rewritten'; "
            "END IF; "
            "IF NEW.updated_at < OLD.updated_at THEN "
            "RAISE EXCEPTION 'notification member state cannot regress'; "
            "END IF; "
            "IF NEW.read_at IS DISTINCT FROM OLD.read_at "
            "OR NEW.dismissed_at IS DISTINCT FROM OLD.dismissed_at THEN "
            "IF NEW.updated_at IS DISTINCT FROM GREATEST(NEW.read_at, NEW.dismissed_at) THEN "
            "RAISE EXCEPTION 'notification member state transition timestamp is invalid'; "
            "END IF; "
            "ELSIF NEW.updated_at IS DISTINCT FROM OLD.updated_at THEN "
            "RAISE EXCEPTION 'notification member state update has no transition'; "
            "END IF; "
            "RETURN NEW; END; $$"
        )
    )
    op.execute(
        sa.text(
            f"CREATE TRIGGER {USER_STATES_TABLE}_transition BEFORE UPDATE "
            f"ON public.{USER_STATES_TABLE} FOR EACH ROW EXECUTE FUNCTION "
            f"public.{USER_STATES_TABLE}_transition_guard()"
        )
    )


def _drop_security() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(
        sa.text(
            f"DROP TRIGGER IF EXISTS {USER_STATES_TABLE}_transition "
            f"ON public.{USER_STATES_TABLE}"
        )
    )
    op.execute(
        sa.text(
            f"DROP FUNCTION IF EXISTS public.{USER_STATES_TABLE}_transition_guard()"
        )
    )
    op.execute(
        sa.text(f"DROP POLICY IF EXISTS {USER_STATES_TABLE}_scope ON public.{USER_STATES_TABLE}")
    )
    op.execute(
        sa.text(
            f"DROP TRIGGER IF EXISTS {NOTIFICATIONS_TABLE}_immutable "
            f"ON public.{NOTIFICATIONS_TABLE}"
        )
    )
    op.execute(
        sa.text(f"DROP FUNCTION IF EXISTS public.{NOTIFICATIONS_TABLE}_immutable_guard()")
    )
    op.execute(
        sa.text(
            f"DROP POLICY IF EXISTS {NOTIFICATIONS_TABLE}_insert "
            f"ON public.{NOTIFICATIONS_TABLE}"
        )
    )
    op.execute(
        sa.text(
            f"DROP POLICY IF EXISTS {NOTIFICATIONS_TABLE}_select "
            f"ON public.{NOTIFICATIONS_TABLE}"
        )
    )

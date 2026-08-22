from __future__ import annotations

from pathlib import Path

from sqlalchemy import inspect

from app.models.notification import Notification, NotificationUserState


MIGRATION_NAME = "20260822_0210_notification_center.py"
MIGRATION_ROOT = Path(__file__).resolve().parents[1] / "alembic" / "versions"


def _migration_source() -> str:
    return (MIGRATION_ROOT / MIGRATION_NAME).read_text(encoding="utf-8")


def test_notification_migration_is_linear_after_rate_limit_contention_hotfix() -> None:
    source = _migration_source()

    assert 'revision = "20260822_0210"' in source
    assert 'down_revision = "20260822_0209"' in source
    assert 'NOTIFICATIONS_TABLE = "notifications"' in source
    assert 'USER_STATES_TABLE = "notification_user_states"' in source


def test_notification_migration_matches_models_and_dedupe_contract(db_session) -> None:
    inspector = inspect(db_session.get_bind())
    assert {Notification.__tablename__, NotificationUserState.__tablename__}.issubset(
        set(inspector.get_table_names())
    )
    notification_columns = {
        column["name"] for column in inspector.get_columns(Notification.__tablename__)
    }
    user_state_columns = {
        column["name"]
        for column in inspector.get_columns(NotificationUserState.__tablename__)
    }
    assert notification_columns == set(Notification.__table__.columns.keys())
    assert user_state_columns == set(NotificationUserState.__table__.columns.keys())

    source = _migration_source()
    for column_name in Notification.__table__.columns.keys():
        assert f'"{column_name}"' in source
    for column_name in NotificationUserState.__table__.columns.keys():
        assert f'"{column_name}"' in source
    assert "uq_notifications_source_event" in source
    assert "uq_notifications_semantic_cooldown" in source
    assert "fk_notifications_source_event" in source
    assert "fk_notifications_location_org" in source
    assert "fk_notification_user_states_notification_scope" in source
    assert "cooldown_expires_at > cooldown_window_started_at" in source
    assert "event_type in ('report.ready','action.failed')" in source


def test_notification_migration_enforces_tenant_user_scope_and_immutable_truth() -> None:
    source = _migration_source()
    normalized = " ".join(source.split())

    assert "ENABLE ROW LEVEL SECURITY" in source
    assert "app.current_tenant_id" in source
    assert "app.current_organization_id" in source
    assert "app.current_user_id" in source
    assert "GRANT SELECT, INSERT ON TABLE public.{NOTIFICATIONS_TABLE}" in source
    assert "REVOKE UPDATE, DELETE ON TABLE public.{NOTIFICATIONS_TABLE}" in source
    assert "GRANT SELECT, INSERT ON TABLE public.{USER_STATES_TABLE}" in source
    assert "REVOKE UPDATE, DELETE ON TABLE public.{USER_STATES_TABLE}" in source
    assert "GRANT UPDATE (read_at, dismissed_at, updated_at)" in source
    assert "notifications are immutable" in source
    assert "BEFORE UPDATE OR DELETE" in normalized
    assert "notification member state identity is immutable" in source
    assert "notification member state cannot be cleared or rewritten" in source
    assert "notification member state cannot regress" in source
    assert "notification member state update has no transition" in source
    assert "BEFORE UPDATE" in normalized
    assert "Cannot downgrade while notifications exist" in source
    assert "Cannot downgrade while notification member state exists" in source
    assert "email" not in source.lower()
    assert "digest" not in source.lower()
    assert "provider" not in source.lower()

from pathlib import Path

from sqlalchemy import inspect

from app.models.automation_webhook import (
    AutomationWebhookConnection,
    AutomationWebhookDelivery,
    AutomationWebhookDeliveryAttempt,
)


def test_automation_webhook_schema_matches_models_and_security_contract(db_session) -> None:
    inspector = inspect(db_session.get_bind())
    expected = {
        AutomationWebhookConnection.__tablename__,
        AutomationWebhookDelivery.__tablename__,
        AutomationWebhookDeliveryAttempt.__tablename__,
    }
    assert expected.issubset(set(inspector.get_table_names()))
    connection_columns = {
        item["name"] for item in inspector.get_columns("automation_webhook_connections")
    }
    assert {
        "encrypted_config_blob",
        "endpoint_host",
        "event_types_json",
        "signing_secret_version",
        "verification_status",
    }.issubset(connection_columns)
    delivery_columns = {
        item["name"] for item in inspector.get_columns("automation_webhook_deliveries")
    }
    assert "encrypted_event_blob" in delivery_columns
    assert "event_hash" in delivery_columns
    assert "destination_url" not in connection_columns
    assert "signing_secret" not in connection_columns


def test_automation_webhook_migration_is_scoped_reversible_and_append_only() -> None:
    source = Path(
        "backend/alembic/versions/20260816_0160_automation_webhook_delivery.py"
    ).read_text(encoding="utf-8")
    assert 'down_revision = "20260815_0159"' in source
    assert "ENABLE ROW LEVEL SECURITY" in source
    assert "current_tenant_id" in source
    assert "current_organization_id" in source
    assert "REVOKE DELETE" in source
    assert "REVOKE UPDATE, DELETE" in source
    assert "op.drop_table(\"automation_webhook_delivery_attempts\")" in source
    assert "op.drop_table(\"automation_webhook_deliveries\")" in source
    assert "op.drop_table(\"automation_webhook_connections\")" in source

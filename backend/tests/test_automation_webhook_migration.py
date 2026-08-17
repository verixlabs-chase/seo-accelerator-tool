from pathlib import Path

from sqlalchemy import inspect

from app.models.automation_webhook import (
    AutomationWebhookConnection,
    AutomationWebhookDelivery,
    AutomationWebhookDeliveryAttempt,
)


MIGRATIONS_ROOT = Path(__file__).resolve().parents[1] / "alembic" / "versions"


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
        "paused_at",
        "paused_by_user_id",
        "signing_secret_version",
        "verification_status",
    }.issubset(connection_columns)
    delivery_columns = {
        item["name"] for item in inspector.get_columns("automation_webhook_deliveries")
    }
    assert {
        "cancelled_at",
        "dead_lettered_at",
        "delivery_kind",
        "encrypted_event_blob",
        "event_hash",
        "next_attempt_at",
        "platform_job_id",
        "recovery_count",
        "source_outbox_event_id",
    }.issubset(delivery_columns)
    assert "destination_url" not in connection_columns
    assert "signing_secret" not in connection_columns


def test_automation_webhook_migration_is_scoped_reversible_and_append_only() -> None:
    source = (MIGRATIONS_ROOT / "20260816_0160_automation_webhook_delivery.py").read_text(
        encoding="utf-8"
    )
    assert 'down_revision = "20260815_0159"' in source
    assert "ENABLE ROW LEVEL SECURITY" in source
    assert "current_tenant_id" in source
    assert "current_organization_id" in source
    assert "REVOKE DELETE" in source
    assert "REVOKE UPDATE, DELETE" in source
    assert "op.drop_table(\"automation_webhook_delivery_attempts\")" in source
    assert "op.drop_table(\"automation_webhook_deliveries\")" in source
    assert "op.drop_table(\"automation_webhook_connections\")" in source


def test_automation_fanout_migration_preserves_attempt_truth_and_is_reversible() -> None:
    source = (MIGRATIONS_ROOT / "20260816_0161_automation_webhook_fanout.py").read_text(
        encoding="utf-8"
    )
    assert 'down_revision = "20260816_0160"' in source
    assert "source_outbox_event_id" in source
    assert "platform_job_id" in source
    assert "delivery_kind in ('test','product')" in source
    assert "max_attempts >= 3" in source
    assert "status in ('pending','delivered','failed','dead_letter','cancelled')" in source
    assert "Cannot downgrade automation fanout after an owner recovery" in source
    assert 'batch_op.drop_column("paused_by_user_id")' in source
    assert '"delivery_kind",' in source


def test_n8n_cloud_migration_expands_provider_allowlist_reversibly() -> None:
    source = (MIGRATIONS_ROOT / "20260817_0162_automation_n8n_cloud.py").read_text(
        encoding="utf-8"
    )
    assert 'down_revision = "20260816_0161"' in source
    assert "provider in ('zapier','make','pipedream','n8n')" in source
    assert "WHERE provider = 'n8n'" in source
    assert "Cannot downgrade n8n Cloud support while an n8n connection exists" in source
    assert "provider in ('zapier','make','pipedream')" in source

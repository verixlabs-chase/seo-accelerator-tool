from __future__ import annotations

from pathlib import Path


MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "20260817_0165_governed_ai_provider_candidates.py"
)
VALIDATION_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "20260817_0166_governed_ai_provider_validation.py"
)


def test_provider_candidate_migration_is_scoped_encrypted_and_inactive() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert 'down_revision = "20260817_0164"' in source
    assert '"governed_ai_provider_connections"' in source
    assert '"encrypted_config_blob"' in source
    assert '"network_validation_status"' in source
    assert '"resolved_address_hash"' in source
    assert "automatic_activation_allowed = false" in source
    assert "activation_status = 'inactive'" in source
    assert "ENABLE ROW LEVEL SECURITY" in source
    assert "current_setting('app.current_tenant_id', true)" in source
    assert "current_setting('app.current_organization_id', true)" in source
    assert "REVOKE DELETE" in source
    assert "op.drop_table(table)" in source


def test_provider_validation_migration_is_bounded_and_reversible() -> None:
    source = VALIDATION_MIGRATION.read_text(encoding="utf-8")

    assert 'down_revision = "20260817_0165"' in source
    assert '"last_validation_latency_ms"' in source
    assert '"validation_schema_version"' in source
    assert '"validation_evidence_hash"' in source
    assert "last_validation_latency_ms <= 60000" in source
    assert 'batch.drop_column("validation_evidence_hash")' in source
    assert 'batch.drop_column("validation_schema_version")' in source
    assert 'batch.drop_column("last_validation_latency_ms")' in source

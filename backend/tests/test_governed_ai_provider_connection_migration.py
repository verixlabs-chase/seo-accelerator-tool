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
BENCHMARK_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "20260817_0167_governed_ai_provider_benchmarks.py"
)
REVIEW_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "20260818_0168_governed_ai_provider_reviews.py"
)
STANDBY_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "20260818_0169_governed_ai_provider_standby.py"
)
READINESS_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "20260818_0170_ai_provider_routing_readiness.py"
)
CANARY_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "20260818_0171_private_ai_canary.py"
)
CANARY_MONITORING_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "20260818_0172_private_ai_canary_monitoring.py"
)
QUESTION_CAPABILITY_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "20260818_0173_private_ai_question_capability.py"
)
DRAFT_CAPABILITY_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "20260818_0174_private_ai_draft_capability.py"
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


def test_provider_benchmark_migration_is_scoped_immutable_and_inactive() -> None:
    source = BENCHMARK_MIGRATION.read_text(encoding="utf-8")

    assert 'down_revision = "20260817_0166"' in source
    assert 'TABLE = "governed_ai_provider_benchmarks"' in source
    assert "automatic_activation_allowed = false" in source
    assert "case_count = 3" in source
    assert "connection_evidence_hash" in source
    assert "idempotency_key" in source
    assert "ENABLE ROW LEVEL SECURITY" in source
    assert "GRANT SELECT, INSERT" in source
    assert "REVOKE UPDATE, DELETE" in source
    assert "app.platform_maintenance" in source
    assert "BEFORE UPDATE OR DELETE" in source
    assert "op.drop_table(TABLE)" in source


def test_provider_review_migration_is_scoped_immutable_and_never_activates() -> None:
    source = REVIEW_MIGRATION.read_text(encoding="utf-8")

    assert 'down_revision = "20260817_0167"' in source
    assert 'TABLE = "governed_ai_provider_reviews"' in source
    assert "approved_for_future_activation" in source
    assert "automatic_activation_allowed = false" in source
    assert "benchmark_artifact_hash" in source
    assert "connection_evidence_hash" in source
    assert "fk_ai_provider_reviews_benchmark_scope" in source
    assert "ENABLE ROW LEVEL SECURITY" in source
    assert "GRANT SELECT, INSERT" in source
    assert "REVOKE UPDATE, DELETE" in source
    assert "app.platform_maintenance" in source
    assert "BEFORE UPDATE OR DELETE" in source
    assert "op.drop_table(TABLE)" in source


def test_provider_standby_migration_is_append_only_and_zero_traffic() -> None:
    source = STANDBY_MIGRATION.read_text(encoding="utf-8")

    assert 'down_revision = "20260818_0168"' in source
    assert 'TABLE = "governed_ai_provider_standby_events"' in source
    assert "zero_traffic_standby" in source
    assert "traffic_percentage = 0" in source
    assert "customer_prompts_allowed = false" in source
    assert "automatic_changes_allowed = false" in source
    assert "managed_backend = 'mistral'" in source
    assert "fk_ai_provider_standby_events_review_scope" in source
    assert "uq_ai_provider_reviews_id_scope" in source
    assert "ENABLE ROW LEVEL SECURITY" in source
    assert "GRANT SELECT, INSERT" in source
    assert "REVOKE UPDATE, DELETE" in source
    assert "app.platform_maintenance" in source
    assert "BEFORE UPDATE OR DELETE" in source
    assert "op.drop_table(TABLE)" in source


def test_provider_readiness_migration_is_scoped_immutable_and_non_routing() -> None:
    source = READINESS_MIGRATION.read_text(encoding="utf-8")

    assert 'down_revision = "20260818_0169"' in source
    assert 'TABLE = "governed_ai_provider_routing_readiness"' in source
    assert "traffic_percentage = 0" in source
    assert "routing_enabled = false" in source
    assert "customer_prompts_allowed = false" in source
    assert "automatic_changes_allowed = false" in source
    assert "candidate_run_count = 0" in source
    assert "managed_route_status = 'healthy'" in source
    assert "fk_ai_provider_readiness_standby_scope" in source
    assert "uq_ai_provider_standby_events_id_scope" in source
    assert "ENABLE ROW LEVEL SECURITY" in source
    assert "GRANT SELECT, INSERT" in source
    assert "REVOKE UPDATE, DELETE" in source
    assert "app.platform_maintenance" in source
    assert "BEFORE UPDATE OR DELETE" in source
    assert "op.drop_table(TABLE)" in source


def test_private_ai_canary_migration_is_fixed_bounded_and_reversible() -> None:
    source = CANARY_MIGRATION.read_text(encoding="utf-8")

    assert 'down_revision = "20260818_0170"' in source
    assert 'EVENTS = "governed_ai_provider_canary_events"' in source
    assert 'ATTEMPTS = "governed_ai_provider_canary_attempts"' in source
    assert "traffic_percentage = 5" in source
    assert "max_prompts_per_day = 1" in source
    assert "automatic_rollback_enabled = true" in source
    assert "automatic_activation_allowed = false" in source
    assert "automatic_changes_allowed = false" in source
    assert "platform_provider_cost = 0" in source
    assert "fk_ai_provider_canary_readiness_scope" in source
    assert "fk_ai_provider_canary_attempt_event_scope" in source
    assert "uq_ai_provider_routing_readiness_id_scope" in source
    assert "ENABLE ROW LEVEL SECURITY" in source
    assert "GRANT SELECT, INSERT" in source
    assert "REVOKE UPDATE, DELETE" in source
    assert "app.platform_maintenance" in source
    assert "BEFORE UPDATE OR DELETE" in source
    assert "op.drop_table(ATTEMPTS)" in source
    assert "op.drop_table(EVENTS)" in source


def test_private_ai_canary_monitoring_is_evidence_only_and_reversible() -> None:
    source = CANARY_MONITORING_MIGRATION.read_text(encoding="utf-8")

    assert 'down_revision = "20260818_0171"' in source
    assert 'HEALTH = "governed_ai_provider_canary_health_snapshots"' in source
    assert '"duration_ms"' in source
    assert "required_success_days = 3" in source
    assert "max_latency_threshold_ms = 8000" in source
    assert "eligible_for_later_review" in source
    assert "traffic_change_allowed = false" in source
    assert "capability_change_allowed = false" in source
    assert "automatic_activation_allowed = false" in source
    assert "automatic_changes_allowed = false" in source
    assert "fk_ai_provider_canary_health_event_scope" in source
    assert "ENABLE ROW LEVEL SECURITY" in source
    assert "GRANT SELECT, INSERT" in source
    assert "REVOKE UPDATE, DELETE" in source
    assert "BEFORE UPDATE OR DELETE" in source
    assert "op.drop_table(HEALTH)" in source
    assert 'batch.drop_column("duration_ms")' in source


def test_private_ai_question_capability_is_scoped_bounded_and_reversible() -> None:
    source = QUESTION_CAPABILITY_MIGRATION.read_text(encoding="utf-8")

    assert 'down_revision = "20260818_0172"' in source
    assert 'BENCHMARKS = "governed_ai_provider_capability_benchmarks"' in source
    assert 'EVENTS = "governed_ai_provider_capability_events"' in source
    assert 'ATTEMPTS = "governed_ai_provider_capability_attempts"' in source
    assert "capability = 'intelligence_question'" in source
    assert "customer_prompt_sent = false AND routing_enabled = false" in source
    assert "traffic_percentage = 5" in source
    assert "max_prompts_per_day = 1" in source
    assert "automatic_rollback_enabled = true" in source
    assert "automatic_activation_allowed = false" in source
    assert "automatic_changes_allowed = false" in source
    assert "platform_provider_cost = 0" in source
    assert "fk_ai_provider_capability_benchmark_health_scope" in source
    assert "fk_ai_provider_capability_attempt_event_scope" in source
    assert "ENABLE ROW LEVEL SECURITY" in source
    assert "GRANT SELECT, INSERT" in source
    assert "REVOKE UPDATE, DELETE" in source
    assert "BEFORE UPDATE OR DELETE" in source
    assert "op.drop_table(ATTEMPTS)" in source
    assert "op.drop_table(EVENTS)" in source
    assert "op.drop_table(BENCHMARKS)" in source


def test_private_ai_draft_capability_expands_scope_without_publish_authority() -> None:
    source = DRAFT_CAPABILITY_MIGRATION.read_text(encoding="utf-8")

    assert 'down_revision = "20260818_0173"' in source
    assert 'BENCHMARKS = "governed_ai_provider_capability_benchmarks"' in source
    assert 'EVENTS = "governed_ai_provider_capability_events"' in source
    assert 'ATTEMPTS = "governed_ai_provider_capability_attempts"' in source
    assert "'intelligence_question','intelligence_draft'" in source
    assert "max_prompts_per_day = 1" in source
    assert "automatic_changes_allowed = false" in source
    assert "platform_provider_cost = 0" in source
    assert "_ensure_no_draft_capability_rows()" in source
    assert "Cannot downgrade while private-AI draft capability history exists" in source

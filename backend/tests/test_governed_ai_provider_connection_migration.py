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
KEYWORD_REVIEW_QUALIFICATION_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "20260818_0175_private_ai_keyword_review_qualification.py"
)
KEYWORD_REVIEW_CANARY_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "20260818_0176_private_ai_keyword_review_canary.py"
)
CONTENT_DRAFT_QUALIFICATION_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "20260818_0177_private_ai_content_draft_qualification.py"
)
CONTENT_DRAFT_CANARY_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "20260819_0178_private_ai_content_draft_canary.py"
)
BASELINE_QUALIFICATION_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "20260819_0179_private_ai_baseline_qualification.py"
)
BASELINE_CANARY_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "20260819_0180_private_ai_baseline_canary.py"
)
REVIEW_RESPONSE_QUALIFICATION_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "20260819_0181_private_ai_review_response_qualification.py"
)
REVIEW_RESPONSE_CANARY_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "20260819_0182_private_ai_review_response_canary.py"
)
COST_OWNERSHIP_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "20260819_0183_private_ai_cost_ownership.py"
)
LOCAL_RELAY_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "20260819_0184_outbound_local_ai_relay_enrollment.py"
)
LOCAL_RELAY_DIAGNOSTIC_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "20260819_0185_signed_local_ai_relay_diagnostics.py"
)
LOCAL_RELAY_RUNTIME_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "20260819_0186_local_ai_runtime_discovery.py"
)
LOCAL_RELAY_QUALIFICATION_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "20260819_0187_local_ai_model_qualification.py"
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


def test_private_ai_keyword_review_adds_qualification_without_routing_scope() -> None:
    source = KEYWORD_REVIEW_QUALIFICATION_MIGRATION.read_text(encoding="utf-8")

    assert 'down_revision = "20260818_0174"' in source
    assert 'BENCHMARKS = "governed_ai_provider_capability_benchmarks"' in source
    assert "'keyword_relevance_review'" in source
    assert "case_count = 1" in source
    assert "EVENTS" not in source
    assert "ATTEMPTS" not in source
    assert "traffic_percentage" not in source
    assert "customer_prompts_allowed" not in source
    assert "_ensure_no_keyword_review_benchmarks()" in source
    assert "Cannot downgrade while private-AI keyword-review qualification" in source
    assert "history " in source


def test_private_ai_keyword_review_canary_is_fixed_bounded_and_reversible() -> None:
    source = KEYWORD_REVIEW_CANARY_MIGRATION.read_text(encoding="utf-8")

    assert 'down_revision = "20260818_0175"' in source
    assert 'EVENTS = "governed_ai_provider_capability_events"' in source
    assert 'ATTEMPTS = "governed_ai_provider_capability_attempts"' in source
    assert "'keyword_relevance_review'" in source
    assert "max_prompts_per_day = 1" in source
    assert "customer_prompt_sent = true" in source
    assert "automatic_changes_allowed = false" in source
    assert "platform_provider_cost = 0" in source
    assert "_ensure_no_keyword_review_runtime_rows()" in source
    assert "Cannot downgrade while private-AI keyword-review canary history" in source


def test_private_ai_content_draft_adds_qualification_without_routing_scope() -> None:
    source = CONTENT_DRAFT_QUALIFICATION_MIGRATION.read_text(encoding="utf-8")

    assert 'down_revision = "20260818_0176"' in source
    assert 'BENCHMARKS = "governed_ai_provider_capability_benchmarks"' in source
    assert "'content_draft_suggestion'" in source
    assert "case_count = 1" in source
    assert "EVENTS" not in source
    assert "ATTEMPTS" not in source
    assert "traffic_percentage" not in source
    assert "customer_prompts_allowed" not in source
    assert "_ensure_no_content_draft_benchmarks()" in source
    assert "Cannot downgrade while private-AI content-draft qualification" in source


def test_private_ai_content_draft_canary_is_fixed_bounded_and_reversible() -> None:
    source = CONTENT_DRAFT_CANARY_MIGRATION.read_text(encoding="utf-8")

    assert 'down_revision = "20260818_0177"' in source
    assert 'EVENTS = "governed_ai_provider_capability_events"' in source
    assert 'ATTEMPTS = "governed_ai_provider_capability_attempts"' in source
    assert "'content_draft_suggestion'" in source
    assert "max_prompts_per_day = 1" in source
    assert "customer_prompt_sent = true" in source
    assert "automatic_changes_allowed = false" in source
    assert "platform_provider_cost = 0" in source
    assert "_ensure_no_content_draft_runtime_rows()" in source
    assert "Cannot downgrade while private-AI content-draft canary history" in source


def test_private_ai_baseline_adds_qualification_without_routing_scope() -> None:
    source = BASELINE_QUALIFICATION_MIGRATION.read_text(encoding="utf-8")

    assert 'down_revision = "20260819_0178"' in source
    assert 'BENCHMARKS = "governed_ai_provider_capability_benchmarks"' in source
    assert "'onboarding_baseline_narrative'" in source
    assert "case_count = 1" in source
    assert "EVENTS" not in source
    assert "ATTEMPTS" not in source
    assert "traffic_percentage" not in source
    assert "customer_prompts_allowed" not in source
    assert "_ensure_no_baseline_benchmarks()" in source
    assert "Cannot downgrade while private-AI onboarding-baseline qualification" in source


def test_private_ai_baseline_canary_is_fixed_bounded_and_reversible() -> None:
    source = BASELINE_CANARY_MIGRATION.read_text(encoding="utf-8")

    assert 'down_revision = "20260819_0179"' in source
    assert 'EVENTS = "governed_ai_provider_capability_events"' in source
    assert 'ATTEMPTS = "governed_ai_provider_capability_attempts"' in source
    assert "'onboarding_baseline_narrative'" in source
    assert "max_prompts_per_day = 1" in source
    assert "customer_prompt_sent = true" in source
    assert "automatic_changes_allowed = false" in source
    assert "platform_provider_cost = 0" in source
    assert "_ensure_no_baseline_runtime_rows()" in source
    assert "Cannot downgrade while private-AI onboarding-baseline canary history" in source


def test_private_ai_review_response_adds_qualification_without_routing_scope() -> None:
    source = REVIEW_RESPONSE_QUALIFICATION_MIGRATION.read_text(encoding="utf-8")

    assert 'down_revision = "20260819_0180"' in source
    assert 'BENCHMARKS = "governed_ai_provider_capability_benchmarks"' in source
    assert "'review_response_draft'" in source
    assert "case_count = 1" in source
    assert "EVENTS" not in source
    assert "ATTEMPTS" not in source
    assert "traffic_percentage" not in source
    assert "customer_prompts_allowed" not in source
    assert "_ensure_no_review_response_benchmarks()" in source
    assert "Cannot downgrade while private-AI review-response qualification" in source


def test_private_ai_review_response_canary_is_fixed_bounded_and_reversible() -> None:
    source = REVIEW_RESPONSE_CANARY_MIGRATION.read_text(encoding="utf-8")

    assert 'down_revision = "20260819_0181"' in source
    assert 'EVENTS = "governed_ai_provider_capability_events"' in source
    assert 'ATTEMPTS = "governed_ai_provider_capability_attempts"' in source
    assert "'review_response_draft'" in source
    assert "max_prompts_per_day = 1" in source
    assert "customer_prompt_sent = true" in source
    assert "automatic_changes_allowed = false" in source
    assert "platform_provider_cost = 0" in source
    assert "_ensure_no_review_response_runtime_rows()" in source
    assert "Cannot downgrade while private-AI review-response canary history" in source


def test_private_ai_connection_cost_ownership_is_customer_only_and_reversible() -> None:
    source = COST_OWNERSHIP_MIGRATION.read_text(encoding="utf-8")

    assert 'down_revision = "20260819_0182"' in source
    assert 'TABLE = "governed_ai_provider_connections"' in source
    assert '"credential_owner"' in source
    assert 'server_default="organization"' in source
    assert '"cost_responsibility"' in source
    assert 'server_default="customer"' in source
    assert '"platform_billing_enabled"' in source
    assert "credential_owner = 'organization'" in source
    assert "cost_responsibility = 'customer'" in source
    assert "platform_billing_enabled = false" in source
    assert 'batch.drop_column("platform_billing_enabled")' in source
    assert 'batch.drop_column("cost_responsibility")' in source
    assert 'batch.drop_column("credential_owner")' in source


def test_local_ai_relay_enrollment_is_outbound_connection_only_and_revocable() -> None:
    source = LOCAL_RELAY_MIGRATION.read_text(encoding="utf-8")

    assert 'down_revision = "20260819_0183"' in source
    assert 'TABLE = "governed_ai_relay_enrollments"' in source
    assert '"token_hash"' in source
    assert '"token_hint"' in source
    assert "customer_prompts_allowed = false" in source
    assert "decision_packets_enabled = false" in source
    assert "database_access_allowed = false" in source
    assert "execution_allowed = false" in source
    assert "publishing_allowed = false" in source
    assert "status in ('active','revoked')" in source
    assert "ENABLE ROW LEVEL SECURITY" in source
    assert "GRANT SELECT, INSERT, UPDATE" in source
    assert "REVOKE DELETE" in source
    assert "current_setting('app.current_tenant_id', true)" in source
    assert "current_setting('app.current_organization_id', true)" in source
    assert "op.drop_table(TABLE)" in source


def test_local_ai_relay_diagnostics_are_signed_synthetic_and_append_only() -> None:
    source = LOCAL_RELAY_DIAGNOSTIC_MIGRATION.read_text(encoding="utf-8")

    assert 'down_revision = "20260819_0184"' in source
    assert 'PACKETS = "governed_ai_relay_diagnostic_packets"' in source
    assert 'ACKS = "governed_ai_relay_diagnostic_acknowledgements"' in source
    assert "packet_kind = 'synthetic_connection_challenge'" in source
    assert "customer_data_included = false" in source
    assert "model_execution_requested = false" in source
    assert "database_access_requested = false" in source
    assert "business_execution_requested = false" in source
    assert "publishing_requested = false" in source
    assert "customer_data_processed = false" in source
    assert "model_called = false" in source
    assert "GRANT SELECT, INSERT" in source
    assert "REVOKE UPDATE, DELETE" in source
    assert "ENABLE ROW LEVEL SECURITY" in source
    assert "app.platform_maintenance" in source
    assert "append-only" in source
    assert "op.drop_table(ACKS)" in source
    assert "op.drop_table(PACKETS)" in source


def test_local_ai_runtime_discovery_is_minimized_loopback_and_append_only() -> None:
    source = LOCAL_RELAY_RUNTIME_MIGRATION.read_text(encoding="utf-8")

    assert 'down_revision = "20260819_0185"' in source
    assert 'TABLE = "governed_ai_relay_runtime_discoveries"' in source
    assert "runtime_kind in ('not_found','ollama','lm_studio','multiple')" in source
    assert "model_count >= 0 AND model_count <= 1000" in source
    assert "loopback_only = true" in source
    assert "customer_data_sent = false" in source
    assert "model_called = false" in source
    assert "model_identifiers_included = false" in source
    assert "GRANT SELECT, INSERT" in source
    assert "REVOKE UPDATE, DELETE" in source
    assert "ENABLE ROW LEVEL SECURITY" in source
    assert "app.platform_maintenance" in source
    assert "append-only" in source
    assert "op.drop_table(TABLE)" in source


def test_local_model_qualification_is_synthetic_minimized_and_non_activating() -> None:
    source = LOCAL_RELAY_QUALIFICATION_MIGRATION.read_text(encoding="utf-8")

    assert 'down_revision = "20260819_0186"' in source
    assert 'TABLE = "governed_ai_relay_model_qualifications"' in source
    assert "prompt_version = 'local-model-synthetic-v1'" in source
    assert "synthetic_input_only = true" in source
    assert "model_call_attempted = true" in source
    assert '"model_response_received"' in source
    assert "customer_data_sent = false" in source
    assert "raw_model_identifier_sent = false" in source
    assert "model_output_sent = false" in source
    assert "customer_work_allowed = false" in source
    assert "publishing_allowed = false" in source
    assert "GRANT SELECT, INSERT" in source
    assert "REVOKE UPDATE, DELETE" in source
    assert "ENABLE ROW LEVEL SECURITY" in source
    assert "append-only" in source
    assert "op.drop_table(TABLE)" in source

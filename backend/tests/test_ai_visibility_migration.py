from pathlib import Path


def test_ai_search_visibility_migration_is_scoped_immutable_and_unseeded() -> None:
    migration = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "20260814_0153_ai_search_visibility_foundation.py"
    ).read_text(encoding="utf-8")

    assert 'revision = "20260814_0153"' in migration
    assert 'down_revision = "20260814_0152"' in migration
    assert '"ai_search_engine_registry"' in migration
    assert '"ai_search_provider_contract_registry"' in migration
    assert '"ai_search_question_sets"' in migration
    assert '"ai_search_collection_runs"' in migration
    assert '"ai_search_observations"' in migration
    assert "op.bulk_insert" not in migration
    assert "customer_visible = false" in migration
    assert "automatic_activation_allowed = false" in migration
    assert "status = 'candidate'" in migration
    assert "production_qa_passed = false AND pricing_qa_passed = false" in migration
    assert "supported_geographies" in migration
    assert "supported_languages" in migration
    assert "supported_devices" in migration
    assert "supported_personalization_policies" in migration
    assert "supported_evidence_facts" in migration
    assert "unsupported" in migration
    assert "unavailable" in migration
    assert "collection_contract_version" in migration
    assert "parser_version" in migration
    assert "normalizer_version" in migration
    assert "personalization_policy" in migration
    assert "comparison_scope_hash" in migration
    assert "requested_observation_count" in migration
    assert "collected_observation_count" in migration
    assert "provider_contract_id" in migration
    assert "price_card_id" in migration
    assert "cost_reservation_id" in migration
    assert "credential_owner" in migration
    assert "ix_ai_search_provider_contract_supersedes" in migration
    assert (
        "ix_ai_search_provider_contract_registry_supersedes_provider_contract_id"
        not in migration
    )
    assert "fk_ai_search_collection_runs_scoped_question_set" in migration
    assert "fk_ai_search_collection_runs_scoped_prior_run" in migration
    assert "fk_ai_search_observations_scoped_run" in migration
    assert "uq_campaigns_ai_search_scoped_identity" in migration
    assert "uq_users_ai_search_scoped_identity" in migration
    assert "fk_ai_search_question_sets_scoped_campaign" in migration
    assert "fk_ai_search_question_sets_scoped_location" in migration
    assert "fk_ai_search_question_sets_scoped_creator" in migration
    assert "ENABLE ROW LEVEL SECURITY" in migration
    assert "app.current_tenant_id" in migration
    assert "app.current_organization_id" in migration
    assert "REVOKE UPDATE, DELETE" in migration
    assert "BEFORE UPDATE OR DELETE" in migration
    assert "AI search collection run identity is immutable" in migration
    assert "append-only and immutable" in migration
    assert "app.platform_maintenance" in migration
    assert "trg_ai_search_collection_runs_preflight" in migration
    assert "AI search usage allowance is not configured" in migration

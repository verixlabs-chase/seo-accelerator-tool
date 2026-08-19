from types import SimpleNamespace

from app.services import governed_ai_provider_baseline_capability_service
from app.services import governed_ai_provider_canary_service
from app.services import governed_ai_provider_capability_service
from app.services import governed_ai_provider_connection_service
from app.services import governed_ai_provider_content_draft_capability_service
from app.services import governed_ai_provider_draft_capability_service
from app.services import governed_ai_provider_keyword_capability_service
from app.services import governed_ai_provider_review_response_capability_service
from app.services.governed_ai_provider_capability_catalog import (
    CAPABILITY_CATALOG,
    CAPABILITY_CATALOG_VERSION,
    CAPABILITY_CODES,
)


def test_catalog_matches_every_managed_ai_private_route() -> None:
    routed_capabilities = {
        governed_ai_provider_canary_service.CANARY_FEATURE,
        governed_ai_provider_capability_service.CAPABILITY,
        governed_ai_provider_draft_capability_service.CAPABILITY,
        governed_ai_provider_keyword_capability_service.CAPABILITY,
        governed_ai_provider_content_draft_capability_service.CAPABILITY,
        governed_ai_provider_baseline_capability_service.CAPABILITY,
        governed_ai_provider_review_response_capability_service.CAPABILITY,
    }

    assert len(CAPABILITY_CODES) == 7
    assert len(set(CAPABILITY_CODES)) == 7
    assert set(CAPABILITY_CODES) == routed_capabilities


def test_catalog_keeps_every_capability_separate_bounded_and_non_mutating() -> None:
    for item in CAPABILITY_CATALOG:
        assert item.fixed_canary_percentage == 5
        assert item.shared_workspace_prompt_limit_per_day == 1
        assert item.separate_qualification_required is True
        assert item.owner_approval_required is True
        assert item.managed_fallback_required is True
        assert item.automatic_rollback is True
        assert item.automatic_changes_allowed is False
        assert item.publishing_allowed is False


def test_connection_truth_uses_the_versioned_catalog_for_legacy_rows() -> None:
    row = SimpleNamespace(
        id="provider-1",
        name="Private model",
        adapter_type="openai_compatible",
        status="candidate",
        endpoint_host="example.test",
        model_identifier="private-model",
        capabilities_json='["explain"]',
        credential_configured=True,
        validation_status="passed",
        network_validation_status="passed",
        last_validation_reason=None,
        last_validation_latency_ms=50,
        validation_schema_version="openai-compatible-connection-v1",
        activation_status="inactive",
        automatic_activation_allowed=False,
        created_at=SimpleNamespace(isoformat=lambda: "2026-08-18T00:00:00+00:00"),
        last_validated_at=None,
    )

    payload = governed_ai_provider_connection_service._serialize(row)

    assert payload["capability_catalog_version"] == CAPABILITY_CATALOG_VERSION
    assert payload["capabilities"] == list(CAPABILITY_CODES)
    assert [item["code"] for item in payload["supported_capabilities"]] == list(
        CAPABILITY_CODES
    )
    assert payload["capability_truth"]["state"] == "separate_approval_required"
    assert payload["billing_boundary"] == {
        "cost_responsibility": "customer",
        "platform_billing_enabled": False,
        "summary": (
            "Usage fees for this private endpoint stay with the customer's provider "
            "account. InsightOS does not bill or pay this provider."
        ),
    }
    assert payload["automatic_activation_allowed"] is False

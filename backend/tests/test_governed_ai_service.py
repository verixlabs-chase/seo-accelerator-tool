from __future__ import annotations

from datetime import UTC, datetime
import json
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException

from app.intelligence.contracts.governed_ai import GovernedIntelligenceBrief
from app.models.cost_economics import CostLedgerEntry
from app.models.governed_ai import GovernedAIRun
from app.models.intelligence import StrategyRecommendation
from app.services import governed_ai_service
from app.services.governed_ai_provider import GovernedAIProviderResponse
from app.services.governed_ai_provider import MistralGovernedAIProvider
from tests.conftest import create_test_campaign


def _settings(*, configured: bool) -> SimpleNamespace:
    return SimpleNamespace(
        ai_provider_backend="mistral",
        mistral_api_key="configured-key" if configured else "",
        mistral_api_endpoint="https://api.mistral.ai/v1/chat/completions",
        mistral_model="mistral-small-2603",
        ai_provider_timeout_seconds=30.0,
        ai_provider_max_attempts=2,
        ai_max_input_tokens=12_000,
        ai_max_output_tokens=800,
    )


class ContextAwareProvider:
    name = "mistral"
    model_name = "mistral-small-2603"

    def __init__(self, *, invalid_action: bool = False) -> None:
        self.invalid_action = invalid_action
        self.calls = 0

    def generate(
        self,
        *,
        context,
        output_schema,
        prompt_template_version,
    ) -> GovernedAIProviderResponse:
        self.calls += 1
        selected = context["deterministic_selection"]["selected_action_id"]
        recommendation = context["facts"]["recommendations"][0]
        return GovernedAIProviderResponse(
            payload={
                "summary": "The saved evidence points to one practical technical priority.",
                "why_now": "The deterministic engine selected this from the current evidence.",
                "selected_action_id": (
                    "invented.action" if self.invalid_action else selected
                ),
                "evidence_used": [recommendation["evidence_id"]],
                "uncertainties": ["A ranking outcome is not guaranteed."],
                "approval_required": context["deterministic_selection"][
                    "approval_required"
                ],
            },
            provider_request_id="mistral-request-1",
            model_name=self.model_name,
            input_tokens=1_000,
            output_tokens=200,
        )


def _campaign_with_lexicon_action(db_session, create_test_org):
    organization = create_test_org(name="Governed AI org")
    campaign = create_test_campaign(
        db_session,
        organization.id,
        name="Governed AI campaign",
        domain="governed-ai.example",
    )
    db_session.add(
        StrategyRecommendation(
            tenant_id=campaign.tenant_id,
            campaign_id=campaign.id,
            recommendation_type=(
                "policy::core_web_vitals::technical.optimize_lcp_resource"
            ),
            rationale="The main visible content should load sooner.",
            confidence=0.84,
            confidence_score=0.84,
            evidence_json='["largest_contentful_paint_needs_work"]',
            risk_tier=2,
            rollback_plan_json='{"steps":["restore_prior_resource_priority"]}',
            status="GENERATED",
            created_at=datetime(2026, 7, 30, 20, 0, tzinfo=UTC),
        )
    )
    db_session.commit()
    return organization, campaign


def test_missing_provider_uses_persisted_deterministic_fallback(
    db_session,
    create_test_org,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        governed_ai_service,
        "get_settings",
        lambda: _settings(configured=False),
    )
    organization, campaign = _campaign_with_lexicon_action(
        db_session,
        create_test_org,
    )

    payload = governed_ai_service.generate_governed_brief(
        db_session,
        organization_id=organization.id,
        campaign_id=campaign.id,
        requested_by_user_id=None,
        now=datetime(2026, 7, 30, 20, 15, tzinfo=UTC),
    )

    assert payload["item"]["status"] == "fallback"
    assert payload["item"]["provider_state"] == "not_configured"
    assert payload["item"]["output"]["selected_action"]["action_id"] == (
        "technical.optimize_lcp_resource"
    )
    assert payload["item"]["output"]["approval_required"] is True
    assert db_session.query(CostLedgerEntry).count() == 0
    assert db_session.query(GovernedAIRun).count() == 1


def test_valid_provider_output_is_metered_validated_and_idempotent(
    db_session,
    create_test_org,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        governed_ai_service,
        "get_settings",
        lambda: _settings(configured=True),
    )
    organization, campaign = _campaign_with_lexicon_action(
        db_session,
        create_test_org,
    )
    provider = ContextAwareProvider()
    now = datetime(2026, 7, 30, 20, 30, tzinfo=UTC)

    first = governed_ai_service.generate_governed_brief(
        db_session,
        organization_id=organization.id,
        campaign_id=campaign.id,
        requested_by_user_id=None,
        provider=provider,
        now=now,
    )
    replay = governed_ai_service.generate_governed_brief(
        db_session,
        organization_id=organization.id,
        campaign_id=campaign.id,
        requested_by_user_id=None,
        provider=provider,
        now=now,
    )

    assert first["item"]["status"] == "validated"
    assert first["item"]["provider_state"] == "ready"
    assert first["item"]["output"]["selected_action_id"] == (
        "technical.optimize_lcp_resource"
    )
    assert first["item"]["usage"]["input_tokens"] == 1_000
    assert first["item"]["usage"]["output_tokens"] == 200
    assert first["item"]["usage"]["reconciled_cost"] == pytest.approx(0.00027)
    assert replay["item"]["id"] == first["item"]["id"]
    assert replay["idempotent_replay"] is True
    assert provider.calls == 1
    assert db_session.query(CostLedgerEntry).count() == 2


def test_invented_action_is_rejected_after_cost_reconciliation(
    db_session,
    create_test_org,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        governed_ai_service,
        "get_settings",
        lambda: _settings(configured=True),
    )
    organization, campaign = _campaign_with_lexicon_action(
        db_session,
        create_test_org,
    )

    payload = governed_ai_service.generate_governed_brief(
        db_session,
        organization_id=organization.id,
        campaign_id=campaign.id,
        requested_by_user_id=None,
        provider=ContextAwareProvider(invalid_action=True),
        now=datetime(2026, 7, 30, 20, 45, tzinfo=UTC),
    )

    assert payload["item"]["status"] == "rejected"
    assert payload["item"]["provider_state"] == "invalid_output"
    assert payload["item"]["error_code"] == "ai_output_validation_failed"
    assert payload["item"]["output"]["selected_action_id"] == (
        "technical.optimize_lcp_resource"
    )
    assert db_session.query(CostLedgerEntry).count() == 2


def test_campaign_scope_cannot_cross_organizations(
    db_session,
    create_test_org,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        governed_ai_service,
        "get_settings",
        lambda: _settings(configured=False),
    )
    first_org, campaign = _campaign_with_lexicon_action(
        db_session,
        create_test_org,
    )
    second_org = create_test_org(
        organization_id=str(uuid4()),
        name="Other governed AI org",
    )
    assert first_org.id != second_org.id

    with pytest.raises(HTTPException) as blocked:
        governed_ai_service.generate_governed_brief(
            db_session,
            organization_id=second_org.id,
            campaign_id=campaign.id,
            requested_by_user_id=None,
        )
    assert blocked.value.status_code == 404


def test_output_contract_rejects_unknown_evidence_and_promises() -> None:
    output = GovernedIntelligenceBrief(
        summary="This will rank first and is guaranteed.",
        why_now="The evidence proves that revenue will increase.",
        selected_action_id=None,
        evidence_used=["unknown:evidence"],
        uncertainties=[],
        approval_required=False,
    )

    with pytest.raises(ValueError):
        output.validate_against_context(
            evidence_ids={"campaign:1"},
            deterministic_action_id=None,
            action_requires_approval=False,
        )


def test_output_contract_allows_truthful_uncertainty_language() -> None:
    output = GovernedIntelligenceBrief(
        summary="The current evidence supports reviewing this page first.",
        why_now="Better rankings are not guaranteed, so measure the result.",
        selected_action_id=None,
        evidence_used=["campaign:1"],
        uncertainties=["The outcome depends on later verified measurements."],
        approval_required=False,
    )

    output.validate_against_context(
        evidence_ids={"campaign:1"},
        deterministic_action_id=None,
        action_requires_approval=False,
    )


def test_mistral_adapter_uses_strict_schema_and_records_usage() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "id": "request-123",
                "model": "mistral-small-2603",
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"summary":"Current evidence supports this review.",'
                                '"why_now":"It is the engine-selected priority.",'
                                '"selected_action_id":null,'
                                '"evidence_used":["campaign:1"],'
                                '"uncertainties":[],'
                                '"approval_required":false}'
                            )
                        }
                    }
                ],
                "usage": {
                    "prompt_tokens": 321,
                    "completion_tokens": 45,
                },
            },
        )

    provider = MistralGovernedAIProvider(
        api_key="test-key",
        endpoint="https://api.mistral.ai/v1/chat/completions",
        model_name="mistral-small-2603",
        timeout_seconds=10,
        max_output_tokens=500,
        max_attempts=1,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    response = provider.generate(
        context={
            "facts": {"campaign": {"evidence_id": "campaign:1"}},
            "deterministic_selection": {
                "selected_action_id": None,
                "approval_required": False,
            },
        },
        output_schema=GovernedIntelligenceBrief.model_json_schema(),
        prompt_template_version="test-contract-v1",
    )

    assert captured["model"] == "mistral-small-2603"
    assert captured["temperature"] == 0
    assert captured["response_format"]["type"] == "json_schema"
    assert captured["response_format"]["json_schema"]["strict"] is True
    assert response.provider_request_id == "request-123"
    assert response.input_tokens == 321
    assert response.output_tokens == 45


def test_governed_brief_api_returns_safe_fallback_without_provider(client) -> None:
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "org-admin@example.com", "password": "pass-org-admin"},
    )
    assert login.status_code == 200
    token = login.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    created = client.post(
        "/api/v1/campaigns",
        json={"name": "Governed AI API", "domain": "governed-ai-api.example"},
        headers=headers,
    )
    assert created.status_code == 200
    campaign_id = created.json()["data"]["id"]

    empty = client.get(
        f"/api/v1/intelligence/brief?campaign_id={campaign_id}",
        headers=headers,
    )
    assert empty.status_code == 200
    assert empty.json()["data"]["item"] is None

    generated = client.post(
        f"/api/v1/intelligence/brief?campaign_id={campaign_id}",
        json={"retry_failed": False},
        headers=headers,
    )
    assert generated.status_code == 200
    payload = generated.json()["data"]
    assert payload["item"]["status"] == "fallback"
    assert payload["item"]["provider_state"] == "not_configured"
    assert payload["item"]["truth"]["classification"] == "heuristic"
    assert payload["item"]["truth"]["operator_state"] == (
        "operator_review_required"
    )

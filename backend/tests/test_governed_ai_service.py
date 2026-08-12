from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException

from app.intelligence.contracts.governed_ai import GovernedIntelligenceBrief
from app.intelligence.lexicon.plain_language import (
    SERVICE_BUSINESS_LANGUAGE_GUIDE_VERSION,
    find_disallowed_customer_terms,
    load_service_business_language_guide,
    simplify_internal_language,
)
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

    def __init__(
        self,
        *,
        invalid_action: bool = False,
        technical_language: bool = False,
    ) -> None:
        self.invalid_action = invalid_action
        self.technical_language = technical_language
        self.calls = 0
        self.last_context = None

    def generate(
        self,
        *,
        context,
        output_schema,
        prompt_template_version,
    ) -> GovernedAIProviderResponse:
        self.calls += 1
        self.last_context = context
        selected = context["deterministic_selection"]["selected_action_id"]
        recommendation = context["facts"]["recommendations"][0]
        return GovernedAIProviderResponse(
            payload={
                "summary": (
                    "Optimize the LCP resource and review the technical SEO evidence."
                    if self.technical_language
                    else "Make the main part of this page load faster."
                ),
                "why_now": (
                    "The deterministic engine selected this from the current evidence."
                    if self.technical_language
                    else "Customers may leave when the page takes too long to appear."
                ),
                "selected_action_id": (
                    "invented.action" if self.invalid_action else selected
                ),
                "daily_action_ids": context["deterministic_selection"][
                    "daily_action_ids"
                ],
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
    assert payload["item"]["output"]["daily_action_ids"] == [
        "technical.optimize_lcp_resource"
    ]
    assert payload["item"]["output"]["daily_actions"][0]["steps"]
    assert db_session.query(CostLedgerEntry).count() == 0
    assert db_session.query(GovernedAIRun).count() == 1


def test_nested_evidence_action_populates_fallback_daily_list(
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
    recommendation = (
        db_session.query(StrategyRecommendation)
        .filter(StrategyRecommendation.campaign_id == campaign.id)
        .one()
    )
    recommendation.recommendation_type = "policy::local_review_pace"
    recommendation.evidence_json = json.dumps(
        {
            "evidence": {
                "action_id": "reputation.expand_review_request_coverage",
            }
        }
    )
    db_session.commit()

    payload = governed_ai_service.generate_governed_brief(
        db_session,
        organization_id=organization.id,
        campaign_id=campaign.id,
        requested_by_user_id=None,
        now=datetime(2026, 8, 3, 16, 0, tzinfo=UTC),
    )

    assert payload["item"]["status"] == "fallback"
    assert payload["item"]["output"]["daily_action_ids"] == [
        "reputation.expand_review_request_coverage"
    ]
    assert payload["item"]["output"]["daily_actions"][0]["display_name"] == (
        "Reach more eligible completed customers"
    )
    assert len(payload["item"]["output"]["daily_actions"][0]["steps"]) == 3


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
    next_day = governed_ai_service.generate_governed_brief(
        db_session,
        organization_id=organization.id,
        campaign_id=campaign.id,
        requested_by_user_id=None,
        provider=provider,
        now=now + timedelta(days=1),
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
    assert next_day["item"]["id"] != first["item"]["id"]
    assert next_day["item"]["status"] == "validated"
    assert provider.calls == 2
    assert db_session.query(CostLedgerEntry).count() == 4


def test_daily_brief_uses_three_ranked_active_actions_and_current_work(
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
    for action_id, risk_tier, confidence, status in (
        ("technical.reduce_render_blocking", 3, 0.91, "GENERATED"),
        ("technical.reserve_layout_space", 2, 0.72, "VALIDATED"),
        ("technical.optimize_server_response", 4, 0.99, "ARCHIVED"),
    ):
        db_session.add(
            StrategyRecommendation(
                tenant_id=campaign.tenant_id,
                campaign_id=campaign.id,
                recommendation_type=f"policy::daily::{action_id}",
                rationale="Review the next safe improvement for this website.",
                confidence=confidence,
                confidence_score=confidence,
                evidence_json=(
                    '{"recommended_actions":["technical.reduce_render_blocking",'
                    '"technical.optimize_server_response"]}'
                    if action_id == "technical.reduce_render_blocking"
                    else "{}"
                ),
                risk_tier=risk_tier,
                rollback_plan_json='{"steps":["restore_the_prior_setting"]}',
                status=status,
                created_at=datetime(2026, 7, 30, 20, risk_tier, tzinfo=UTC),
            )
        )
    db_session.commit()
    provider = ContextAwareProvider()

    payload = governed_ai_service.generate_governed_brief(
        db_session,
        organization_id=organization.id,
        campaign_id=campaign.id,
        requested_by_user_id=None,
        provider=provider,
        now=datetime(2026, 7, 30, 21, 0, tzinfo=UTC),
    )

    expected = [
        "technical.reduce_render_blocking",
        "technical.optimize_lcp_resource",
        "technical.reserve_layout_space",
    ]
    assert payload["item"]["status"] == "validated"
    assert payload["item"]["output"]["daily_action_ids"] == expected
    assert [
        item["action_id"] for item in payload["item"]["output"]["daily_actions"]
    ] == expected
    assert provider.last_context is not None
    assert provider.last_context["deterministic_selection"]["daily_action_ids"] == expected
    work_contexts = [
        item["current_work"]
        for item in provider.last_context["facts"]["recommendations"]
        if item.get("action_plan") is not None
    ]
    assert len(work_contexts) == 3
    assert all(item and item["next_step"] for item in work_contexts)
    assert "technical.optimize_server_response" not in payload["item"]["output"][
        "daily_action_ids"
    ]


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


def test_technical_ai_language_is_rejected_and_plain_fallback_is_used(
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
        provider=ContextAwareProvider(technical_language=True),
        now=datetime(2026, 7, 30, 21, 0, tzinfo=UTC),
    )

    assert payload["item"]["status"] == "rejected"
    assert payload["item"]["provider_state"] == "invalid_output"
    assert payload["item"]["error_code"] == "ai_output_validation_failed"
    assert payload["item"]["output"]["summary"] == (
        "Review this issue. The main visible content should load sooner."
    )
    assert "technical" not in payload["item"]["output"]["summary"].lower()


def test_successful_retry_replaces_failed_daily_explanation(
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
    now = datetime(2026, 7, 30, 21, 15, tzinfo=UTC)

    failed = governed_ai_service.generate_governed_brief(
        db_session,
        organization_id=organization.id,
        campaign_id=campaign.id,
        requested_by_user_id=None,
        provider=ContextAwareProvider(technical_language=True),
        now=now,
    )
    recovered = governed_ai_service.generate_governed_brief(
        db_session,
        organization_id=organization.id,
        campaign_id=campaign.id,
        requested_by_user_id=None,
        retry_failed=True,
        provider=ContextAwareProvider(),
        now=now,
    )
    replay = governed_ai_service.generate_governed_brief(
        db_session,
        organization_id=organization.id,
        campaign_id=campaign.id,
        requested_by_user_id=None,
        provider=ContextAwareProvider(),
        now=now,
    )

    assert failed["item"]["status"] == "rejected"
    assert recovered["item"]["status"] == "validated"
    assert replay["item"]["id"] == recovered["item"]["id"]
    assert replay["item"]["output"]["summary"] == (
        "Make the main part of this page load faster."
    )
    assert replay["idempotent_replay"] is True


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
        summary="Fix this page because it will rank first and is guaranteed.",
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
            deterministic_daily_action_ids=[],
            action_requires_approval=False,
        )


def test_output_contract_allows_truthful_uncertainty_language() -> None:
    output = GovernedIntelligenceBrief(
        summary="Review this page first based on the information available.",
        why_now="Better rankings are not guaranteed, so measure the result.",
        selected_action_id=None,
        evidence_used=["campaign:1"],
        uncertainties=["The outcome depends on later verified measurements."],
        approval_required=False,
    )

    output.validate_against_context(
        evidence_ids={"campaign:1"},
        deterministic_action_id=None,
        deterministic_daily_action_ids=[],
        action_requires_approval=False,
    )


def test_output_contract_rejects_changes_to_the_daily_action_plan() -> None:
    output = GovernedIntelligenceBrief(
        summary="Review the first safe action for this business.",
        why_now="Customers may notice the problem now.",
        selected_action_id="technical.optimize_lcp_resource",
        daily_action_ids=["invented.action"],
        evidence_used=["campaign:1"],
        uncertainties=[],
        approval_required=True,
    )

    with pytest.raises(ValueError, match="daily action plan"):
        output.validate_against_context(
            evidence_ids={"campaign:1"},
            deterministic_action_id="technical.optimize_lcp_resource",
            deterministic_daily_action_ids=["technical.optimize_lcp_resource"],
            action_requires_approval=True,
        )


def test_service_business_language_guide_is_the_runtime_writing_standard() -> None:
    guide = load_service_business_language_guide()

    assert SERVICE_BUSINESS_LANGUAGE_GUIDE_VERSION in guide
    assert "Start with the action" in guide
    assert "busy service-business owner" in guide
    assert "Optimize the LCP resource" in guide
    assert "Make the main part of this page load faster" in guide
    assert "Customer interface dictionary" in guide
    assert "Get more reviews from recent customers" in guide
    assert "Count how many recent customers were asked for a review" in guide
    assert "Know how your business is showing up on Google" in guide
    assert "Would this sound natural" in guide


def test_customer_language_contract_rewrites_internal_product_labels() -> None:
    simplified = simplify_internal_language(
        "Review the possible benefit — more evidence needed.",
        max_words=32,
    )

    assert simplified == "Review the result before deciding."
    assert find_disallowed_customer_terms(simplified) == []
    assert find_disallowed_customer_terms("Open the deterministic summary") == [
        "deterministic",
        "deterministic summary",
    ]
    assert find_disallowed_customer_terms(
        "Unlock actionable insights with an AI-powered workflow."
    ) == ["unlock", "actionable insights", "AI-powered"]
    supplier = "".join(("Data", "For", "SEO"))
    assert find_disallowed_customer_terms(f"Refresh {supplier} now.") == [
        "internal search supplier"
    ]
    assert simplify_internal_language(f"Check the {supplier} provider.", max_words=32) == (
        "Check the search data service data source."
    )
    search_estimate = simplify_internal_language(
        "Review the supporting data for measured demand.",
        max_words=32,
    )
    assert search_estimate == (
        "Review the details behind this result for estimated monthly searches."
    )
    assert find_disallowed_customer_terms(search_estimate) == []

    action_support = simplify_internal_language(
        "Likely benefit: strong",
        max_words=32,
        action_first=False,
    )
    assert action_support == "the saved information strongly supports this action"
    assert find_disallowed_customer_terms(action_support) == []

    checklist_step = simplify_internal_language(
        "Measure the share of eligible customers receiving a request.",
        max_words=32,
    )
    assert checklist_step == "Count how many recent customers were asked for a review."
    assert find_disallowed_customer_terms(checklist_step) == []

    request_step = simplify_internal_language(
        "Add approved requests without incentives or review gating.",
        max_words=32,
    )
    assert request_step == (
        "Ask recent customers for reviews without rewards or filtering who gets asked."
    )
    assert find_disallowed_customer_terms(request_step) == []


def test_output_contract_rejects_jargon_and_long_advice() -> None:
    with pytest.raises(ValueError, match="technical language"):
        GovernedIntelligenceBrief(
            summary="Improve GBP review velocity using the provider API.",
            why_now="The deterministic engine selected this action.",
            selected_action_id=None,
            evidence_used=["campaign:1"],
            uncertainties=[],
            approval_required=False,
        )

    with pytest.raises(ValueError, match="32 words or fewer"):
        GovernedIntelligenceBrief(
            summary=" ".join(["Fix"] * 33),
            why_now="Customers are affected now.",
            selected_action_id=None,
            evidence_used=["campaign:1"],
            uncertainties=[],
            approval_required=False,
        )

    with pytest.raises(ValueError, match="clear action verb"):
        GovernedIntelligenceBrief(
            summary="This page needs attention.",
            why_now="Customers are affected now.",
            selected_action_id=None,
            evidence_used=["campaign:1"],
            uncertainties=[],
            approval_required=False,
        )

    with pytest.raises(ValueError, match="1 sentence or fewer"):
        GovernedIntelligenceBrief(
            summary="Fix the page title.",
            why_now="Customers may miss it. Google may also misunderstand it.",
            selected_action_id=None,
            evidence_used=["campaign:1"],
            uncertainties=[],
            approval_required=False,
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
                                '"why_now":"Customers may notice this problem now.",'
                                '"selected_action_id":null,'
                                '"evidence_used":["campaign:1"],'
                                '"uncertainties":[],'
                                '"approval_required":true}'
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
                "daily_action_ids": [],
            },
        },
        output_schema=GovernedIntelligenceBrief.model_json_schema(),
        prompt_template_version="test-contract-v1",
    )

    assert captured["model"] == "mistral-small-2603"
    assert captured["temperature"] == 0
    assert captured["response_format"]["type"] == "json_schema"
    assert captured["response_format"]["json_schema"]["strict"] is True
    system_prompt = captured["messages"][0]["content"]
    assert "InsightOS Service-Business Voice Guide" in system_prompt
    assert SERVICE_BUSINESS_LANGUAGE_GUIDE_VERSION in system_prompt
    assert "Start with the action" in system_prompt
    assert "Make the main part of this page load faster" in system_prompt
    assert response.provider_request_id == "request-123"
    assert response.input_tokens == 321
    assert response.output_tokens == 45
    assert response.payload["selected_action_id"] is None
    assert response.payload["approval_required"] is False
    assert response.payload["daily_action_ids"] == []


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

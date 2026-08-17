from __future__ import annotations

from datetime import UTC, datetime
import json
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException

from app.intelligence.contracts.governed_ai import GovernedActionDraft
from app.models.business_location import BusinessLocation
from app.models.cost_economics import CostLedgerEntry
from app.models.campaign import Campaign
from app.models.governed_ai import GovernedAIRun
from app.models.intelligence import StrategyRecommendation
from app.services import governed_ai_draft_service
from app.services.governed_ai_provider import (
    GovernedAIProviderResponse,
    MistralGovernedAIProvider,
)
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


class DraftProvider:
    name = "mistral"
    model_name = "mistral-small-2603"

    def __init__(self, *, invented_evidence: bool = False) -> None:
        self.invented_evidence = invented_evidence
        self.calls = 0
        self.last_context = None

    def draft_action(
        self,
        *,
        context,
        output_schema,
        prompt_template_version,
    ) -> GovernedAIProviderResponse:
        self.calls += 1
        self.last_context = context
        recommendation = context["facts"]["recommendations"][0]
        return GovernedAIProviderResponse(
            payload={
                "action_id": context["draft_request"]["action_id"],
                "draft_type": context["draft_request"]["draft_type"],
                "draft_state": "ready",
                "title": "Would you share your experience?",
                "body": (
                    "Thank you for choosing our team. If the work is complete, "
                    "please share an honest review about your experience."
                ),
                "evidence_used": [
                    "recommendation:invented"
                    if self.invented_evidence
                    else recommendation["evidence_id"]
                ],
                "uncertainties": [
                    "Confirm the request timing and contact method before use."
                ],
                "approval_required": True,
            },
            provider_request_id="draft-request-1",
            model_name=self.model_name,
            input_tokens=800,
            output_tokens=100,
        )


def _campaign_with_draftable_action(db_session, create_test_org):
    organization = create_test_org(name="Governed draft org")
    campaign = create_test_campaign(
        db_session,
        organization.id,
        name="Governed draft campaign",
        domain="draft.example",
    )
    location = BusinessLocation(
        organization_id=organization.id,
        name="Governed draft location",
        domain=campaign.domain,
        status="active",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db_session.add(location)
    db_session.flush()
    campaign.business_location_id = location.id
    db_session.add(
        StrategyRecommendation(
            tenant_id=campaign.tenant_id,
            campaign_id=campaign.id,
            recommendation_type="policy::local_review_pace",
            rationale="This location is not receiving enough new Google reviews.",
            confidence=0.82,
            confidence_score=0.82,
            evidence_json=json.dumps(
                {
                    "evidence": {
                        "action_id": (
                            "reputation.launch_review_request_workflow"
                        ),
                    }
                }
            ),
            risk_tier=2,
            rollback_plan_json='{"steps":["pause_the_request"]}',
            status="GENERATED",
            created_at=datetime(2026, 8, 3, 16, 0, tzinfo=UTC),
        )
    )
    db_session.commit()
    return organization, campaign


def test_missing_provider_keeps_saved_action_and_safe_fallback(
    db_session,
    create_test_org,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        governed_ai_draft_service,
        "get_settings",
        lambda: _settings(configured=False),
    )
    organization, campaign = _campaign_with_draftable_action(
        db_session,
        create_test_org,
    )

    payload = governed_ai_draft_service.generate_governed_draft(
        db_session,
        organization_id=organization.id,
        campaign_id=campaign.id,
        requested_by_user_id=None,
        action_id="reputation.launch_review_request_workflow",
        draft_type="review_request",
        now=datetime(2026, 8, 3, 16, 15, tzinfo=UTC),
    )

    assert payload["item"]["status"] == "fallback"
    assert payload["item"]["provider_state"] == "not_configured"
    assert payload["item"]["output"]["action_id"] == (
        "reputation.launch_review_request_workflow"
    )
    assert payload["item"]["output"]["approval_required"] is True
    assert "Nothing was changed or published" in payload["item"]["output"]["body"]
    assert db_session.query(CostLedgerEntry).count() == 0
    assert db_session.query(GovernedAIRun).count() == 1


def test_valid_draft_is_metered_cited_and_idempotent(
    db_session,
    create_test_org,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        governed_ai_draft_service,
        "get_settings",
        lambda: _settings(configured=True),
    )
    organization, campaign = _campaign_with_draftable_action(
        db_session,
        create_test_org,
    )
    provider = DraftProvider()
    now = datetime(2026, 8, 3, 16, 30, tzinfo=UTC)

    first = governed_ai_draft_service.generate_governed_draft(
        db_session,
        organization_id=organization.id,
        campaign_id=campaign.id,
        requested_by_user_id=None,
        action_id="reputation.launch_review_request_workflow",
        draft_type="review_request",
        provider=provider,
        now=now,
    )
    replay = governed_ai_draft_service.generate_governed_draft(
        db_session,
        organization_id=organization.id,
        campaign_id=campaign.id,
        requested_by_user_id=None,
        action_id="reputation.launch_review_request_workflow",
        draft_type="review_request",
        provider=provider,
        now=now,
    )

    assert first["item"]["status"] == "validated"
    assert first["item"]["output"]["draft_state"] == "ready"
    assert first["item"]["output"]["evidence_details"][0]["label"] == (
        "Ask recent customers for reviews consistently"
    )
    assert first["item"]["output"]["lineage_schema_version"] == (
        "governed-copy-lineage-v1"
    )
    assert first["item"]["output"]["input_snapshot"] == provider.last_context
    saved_run = db_session.get(GovernedAIRun, first["item"]["id"])
    assert saved_run is not None
    assert (
        governed_ai_draft_service.governed_ai_service._hash_payload(
            first["item"]["output"]["input_snapshot"]
        )
        == saved_run.context_hash
    )
    assert first["item"]["usage"]["reconciled_cost"] > 0
    assert replay["item"]["id"] == first["item"]["id"]
    assert replay["idempotent_replay"] is True
    assert provider.calls == 1
    assert db_session.query(CostLedgerEntry).count() == 2
    assert provider.last_context["allowed_actions"] == [
        provider.last_context["allowed_actions"][0]
    ]
    assert provider.last_context["draft_request"]["may_execute_changes"] is False


def test_draft_rejects_invented_evidence(
    db_session,
    create_test_org,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        governed_ai_draft_service,
        "get_settings",
        lambda: _settings(configured=True),
    )
    organization, campaign = _campaign_with_draftable_action(
        db_session,
        create_test_org,
    )

    payload = governed_ai_draft_service.generate_governed_draft(
        db_session,
        organization_id=organization.id,
        campaign_id=campaign.id,
        requested_by_user_id=None,
        action_id="reputation.launch_review_request_workflow",
        draft_type="review_request",
        provider=DraftProvider(invented_evidence=True),
        now=datetime(2026, 8, 3, 17, 0, tzinfo=UTC),
    )

    assert payload["item"]["status"] == "rejected"
    assert payload["item"]["provider_state"] == "invalid_output"
    assert payload["item"]["error_code"] == "ai_output_validation_failed"


def test_unsupported_action_or_draft_type_is_blocked_before_persistence(
    db_session,
    create_test_org,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        governed_ai_draft_service,
        "get_settings",
        lambda: _settings(configured=False),
    )
    organization, campaign = _campaign_with_draftable_action(
        db_session,
        create_test_org,
    )

    with pytest.raises(HTTPException) as blocked:
        governed_ai_draft_service.generate_governed_draft(
            db_session,
            organization_id=organization.id,
            campaign_id=campaign.id,
            requested_by_user_id=None,
            action_id="reputation.launch_review_request_workflow",
            draft_type="page_outline",
        )

    assert blocked.value.status_code == 422
    assert db_session.query(GovernedAIRun).count() == 0


@pytest.mark.parametrize(
    "body",
    [
        "Use this SEO plan for the service page.",
        "Choose our team for a guaranteed result.",
        "Call us for service in 24 hours.",
    ],
)
def test_ready_draft_rejects_technical_unsupported_or_numeric_claims(body) -> None:
    with pytest.raises(ValueError):
        GovernedActionDraft(
            action_id="reputation.launch_review_request_workflow",
            draft_type="review_request",
            draft_state="ready",
            title="Share your experience",
            body=body,
            evidence_used=["campaign:1"],
            uncertainties=[],
            approval_required=True,
        )


def test_mistral_draft_prompt_preserves_server_owned_control_fields() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content.decode("utf-8")))
        return httpx.Response(
            200,
            json={
                "id": "draft-request-123",
                "model": "mistral-small-2603",
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "action_id": "invented.action",
                                    "draft_type": "page_outline",
                                    "draft_state": "not_enough_information",
                                    "title": "More information is needed",
                                    "body": "Confirm the work and customer before use.",
                                    "evidence_used": [],
                                    "uncertainties": ["The service is not confirmed."],
                                    "approval_required": False,
                                }
                            )
                        }
                    }
                ],
                "usage": {"prompt_tokens": 200, "completion_tokens": 40},
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
    response = provider.draft_action(
        context={
            "draft_request": {
                "action_id": "reputation.launch_review_request_workflow",
                "draft_type": "review_request",
                "approval_required": True,
            },
            "allowed_evidence_ids": ["campaign:1"],
            "allowed_actions": [],
        },
        output_schema=GovernedActionDraft.model_json_schema(),
        prompt_template_version="draft-contract-v1",
    )

    assert captured["response_format"]["json_schema"]["name"] == (
        "governed_action_draft"
    )
    system_prompt = captured["messages"][0]["content"]
    assert "Draft only" in system_prompt
    assert "never make changes" in system_prompt
    assert response.payload["action_id"] == (
        "reputation.launch_review_request_workflow"
    )
    assert response.payload["draft_type"] == "review_request"
    assert response.payload["approval_required"] is True


def test_draft_api_lists_supported_work_and_returns_safe_fallback(
    client,
    db_session,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        governed_ai_draft_service,
        "get_settings",
        lambda: _settings(configured=False),
    )
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "org-admin@example.com", "password": "pass-org-admin"},
    )
    assert login.status_code == 200
    token = login.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    created = client.post(
        "/api/v1/campaigns",
        json={"name": "Draft API", "domain": "draft-api.example"},
        headers=headers,
    )
    assert created.status_code == 200
    campaign_id = created.json()["data"]["id"]
    campaign = db_session.get(Campaign, campaign_id)
    assert campaign is not None
    db_session.add(
        StrategyRecommendation(
            tenant_id=campaign.tenant_id,
            campaign_id=campaign.id,
            recommendation_type="policy::local_review_pace",
            rationale="This location is not receiving enough new Google reviews.",
            confidence=0.82,
            confidence_score=0.82,
            evidence_json=json.dumps(
                {
                    "evidence": {
                        "action_id": (
                            "reputation.launch_review_request_workflow"
                        ),
                    }
                }
            ),
            risk_tier=2,
            rollback_plan_json='{"steps":["pause_the_request"]}',
            status="GENERATED",
            created_at=datetime(2026, 8, 3, 18, 0, tzinfo=UTC),
        )
    )
    db_session.commit()

    available = client.get(
        f"/api/v1/intelligence/drafts?campaign_id={campaign_id}",
        headers=headers,
    )
    assert available.status_code == 200
    assert available.json()["data"]["available_actions"][0]["draft_types"][0][
        "draft_type"
    ] == "review_request"

    generated = client.post(
        f"/api/v1/intelligence/drafts?campaign_id={campaign_id}",
        json={
            "action_id": "reputation.launch_review_request_workflow",
            "draft_type": "review_request",
        },
        headers=headers,
    )
    assert generated.status_code == 200
    payload = generated.json()["data"]
    assert payload["item"]["status"] == "fallback"
    assert payload["item"]["output"]["approval_required"] is True

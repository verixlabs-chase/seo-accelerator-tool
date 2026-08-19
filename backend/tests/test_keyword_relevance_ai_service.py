from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import httpx
import pytest
from pydantic import ValidationError

from app.models.business_location import BusinessLocation
from app.models.business_service import BusinessService
from app.models.business_service_area import BusinessServiceArea
from app.models.campaign import Campaign
from app.models.governed_ai import GovernedAIRun
from app.models.keyword_research import KeywordResearchRun, KeywordResearchSuggestion
from app.intelligence.contracts.governed_ai import GovernedKeywordRelevanceReview
from app.schemas.keyword_research import KeywordResearchAIReviewIn
from app.services import keyword_relevance_ai_service
from app.services.governed_ai_provider import (
    GovernedAIProviderResponse,
    MistralGovernedAIProvider,
)
from app.services.governed_ai_provider_capability_service import CapabilitySelection


class FakeRelevanceProvider:
    name = "mistral"
    model_name = "mistral-small-2603"

    def __init__(self, *, invalid_service: bool = False) -> None:
        self.calls = 0
        self.invalid_service = invalid_service

    def review_keyword_relevance(self, *, context, output_schema, prompt_template_version):  # noqa: ANN001, ANN201
        self.calls += 1
        assert output_schema["additionalProperties"] is False
        assert prompt_template_version == "insightos-keyword-relevance-review-v1"
        service_id = context["confirmed_services"][0]["service_id"]
        area_id = context["included_service_areas"][0]["service_area_id"]
        decisions = []
        for item in context["uncertain_searches"]:
            phrase = item["search_phrase"]
            if "appliance pickup" in phrase:
                decisions.append(
                    {
                        "suggestion_id": item["suggestion_id"],
                        "classification": "relevant",
                        "confidence": 0.93,
                        "matched_service_id": "unknown-service" if self.invalid_service else service_id,
                        "matched_service_area_id": area_id,
                        "area_basis": "included_area",
                        "reason": "Appliance pickup describes the confirmed removal work in Reno.",
                        "evidence_used": [
                            item["evidence_id"],
                            context["confirmed_services"][0]["evidence_id"],
                            context["included_service_areas"][0]["evidence_id"],
                        ],
                    }
                )
            elif "piano lessons" in phrase:
                decisions.append(
                    {
                        "suggestion_id": item["suggestion_id"],
                        "classification": "unrelated",
                        "confidence": 0.98,
                        "matched_service_id": None,
                        "matched_service_area_id": None,
                        "area_basis": "confirmed_market",
                        "reason": "Piano lessons do not describe the confirmed removal work.",
                        "evidence_used": [
                            item["evidence_id"],
                            context["confirmed_services"][0]["evidence_id"],
                        ],
                    }
                )
            else:
                decisions.append(
                    {
                        "suggestion_id": item["suggestion_id"],
                        "classification": "still_unclear",
                        "confidence": 0.62,
                        "matched_service_id": service_id,
                        "matched_service_area_id": area_id,
                        "area_basis": "included_area",
                        "reason": "Trash service could mean several kinds of work, so it needs review.",
                        "evidence_used": [
                            item["evidence_id"],
                            context["confirmed_services"][0]["evidence_id"],
                        ],
                    }
                )
        return GovernedAIProviderResponse(
            payload={"decisions": decisions},
            provider_request_id="relevance-request-1",
            model_name=self.model_name,
            input_tokens=280,
            output_tokens=190,
        )


def test_relevance_review_request_rejects_chat_input() -> None:
    with pytest.raises(ValidationError):
        KeywordResearchAIReviewIn.model_validate(
            {
                "campaign_id": "campaign-1",
                "max_items": 8,
                "question": "Write me a sales email instead.",
            }
        )


def _setup_relevance_case(db_session, create_test_org):  # noqa: ANN001, ANN202
    organization = create_test_org(name="Governed Relevance Org")
    location = BusinessLocation(
        organization_id=organization.id,
        name="Reno Location",
        domain="example.com",
        city="Reno",
        primary_city="Reno",
        region="Nevada",
        country_code="US",
        status="active",
    )
    db_session.add(location)
    db_session.flush()
    campaign = Campaign(
        tenant_id=organization.id,
        organization_id=organization.id,
        business_location_id=location.id,
        name="Junk Magicians",
        domain="example.com",
        setup_state="Active",
    )
    db_session.add(campaign)
    db_session.flush()
    service = BusinessService(
        tenant_id=organization.id,
        organization_id=organization.id,
        business_location_id=location.id,
        scope_type="location",
        scope_key=location.id,
        name="Junk Removal",
        normalized_name="junk removal",
        aliases=["appliance removal"],
        status="confirmed",
        source="manual",
        confidence=1.0,
        evidence=[],
        reviewed_at=datetime.now(UTC),
    )
    area = BusinessServiceArea(
        tenant_id=organization.id,
        organization_id=organization.id,
        business_location_id=location.id,
        area_type="city",
        name="Reno",
        normalized_name="reno",
        region="Nevada",
        country_code="US",
        relationship="included",
        status="confirmed",
        source="manual",
        confidence=1.0,
        evidence=[],
        reviewed_at=datetime.now(UTC),
    )
    db_session.add_all([service, area])
    db_session.flush()
    run = KeywordResearchRun(
        tenant_id=organization.id,
        organization_id=organization.id,
        campaign_id=campaign.id,
        business_location_id=location.id,
        status="complete",
        location_name="Reno, Nevada, United States",
        language_code="en",
        sources=["website_content"],
        warnings=[],
        suggestion_count=3,
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
    )
    db_session.add(run)
    db_session.flush()
    suggestions = []
    for keyword in ("appliance pickup reno", "piano lessons reno", "trash service reno"):
        suggestion = KeywordResearchSuggestion(
            run_id=run.id,
            tenant_id=organization.id,
            organization_id=organization.id,
            campaign_id=campaign.id,
            business_location_id=location.id,
            keyword=keyword,
            normalized_keyword=keyword,
            source_types=["website_content"],
            evidence={"sources": ["website_content"]},
            monthly_searches=[],
            intent="Researching",
            opportunity_group="new_opportunity",
            relevance_score=35,
            relevance_status="needs_review",
            relevance_reason="The match is not clear enough yet.",
            opportunity_score=45,
            recommended_action="Review this search",
            recommendation_reason="Confirm whether it describes work you want.",
        )
        suggestions.append(suggestion)
    db_session.add_all(suggestions)
    db_session.commit()
    return organization, campaign, service, area, suggestions


def test_governed_review_promotes_hides_and_keeps_uncertain_results(
    db_session,
    create_test_org,
) -> None:
    organization, campaign, service, area, suggestions = _setup_relevance_case(
        db_session, create_test_org
    )
    provider = FakeRelevanceProvider()

    payload = keyword_relevance_ai_service.review_uncertain(
        db_session,
        tenant_id=organization.id,
        campaign_id=campaign.id,
        requested_by_user_id=None,
        provider=provider,
    )

    assert payload["ai_review"] == {
        "state": "complete",
        "reviewed": 3,
        "best_matches": 1,
        "hidden_unrelated": 1,
        "still_unclear": 1,
        "message": (
            "Reviewed 3 unclear searches: 1 moved to Best matches, 1 was hidden "
            "as unrelated, and 1 still needs your review."
        ),
    }
    db_session.expire_all()
    appliance = db_session.get(KeywordResearchSuggestion, suggestions[0].id)
    piano = db_session.get(KeywordResearchSuggestion, suggestions[1].id)
    trash = db_session.get(KeywordResearchSuggestion, suggestions[2].id)
    assert appliance is not None and appliance.relevance_status == "relevant"
    assert appliance.matched_service_id == service.id
    assert appliance.matched_service_area_id == area.id
    assert appliance.ai_review_status == "validated"
    assert piano is not None and piano.relevance_status == "unrelated"
    assert trash is not None and trash.relevance_status == "needs_review"
    assert provider.calls == 1

    replay = keyword_relevance_ai_service.review_uncertain(
        db_session,
        tenant_id=organization.id,
        campaign_id=campaign.id,
        requested_by_user_id=None,
        provider=provider,
    )
    assert replay["ai_review"]["state"] == "nothing_to_review"
    assert provider.calls == 1


def test_unknown_service_reference_rejects_entire_ai_batch(
    db_session,
    create_test_org,
) -> None:
    organization, campaign, _service, _area, suggestions = _setup_relevance_case(
        db_session, create_test_org
    )

    payload = keyword_relevance_ai_service.review_uncertain(
        db_session,
        tenant_id=organization.id,
        campaign_id=campaign.id,
        requested_by_user_id=None,
        provider=FakeRelevanceProvider(invalid_service=True),
    )

    assert payload["ai_review"]["state"] == "invalid_output"
    db_session.expire_all()
    assert all(
        db_session.get(KeywordResearchSuggestion, row.id).relevance_status == "needs_review"
        for row in suggestions
    )
    ai_run = db_session.query(GovernedAIRun).one()
    assert ai_run.status == "rejected"
    assert ai_run.error_code == "ai_output_validation_failed"


def _private_runtime_settings() -> SimpleNamespace:
    return SimpleNamespace(
        ai_provider_backend="mistral",
        mistral_model="mistral-small-2603",
        mistral_api_key="managed-test-key",
        mistral_api_endpoint="https://api.mistral.ai/v1/chat/completions",
        ai_provider_timeout_seconds=5,
        ai_provider_max_attempts=1,
        ai_max_input_tokens=20_000,
        ai_max_output_tokens=1_000,
    )


def test_private_keyword_review_success_skips_managed_provider_and_keeps_zero_cost(
    db_session,
    create_test_org,
    monkeypatch,
) -> None:
    organization, campaign, _service, _area, suggestions = _setup_relevance_case(
        db_session, create_test_org
    )
    managed = FakeRelevanceProvider()
    private = FakeRelevanceProvider()
    private.name = "private_ai"
    private.model_name = "customer-model-v1"
    monkeypatch.setattr(keyword_relevance_ai_service, "get_settings", _private_runtime_settings)
    monkeypatch.setattr(
        keyword_relevance_ai_service,
        "MistralGovernedAIProvider",
        lambda **_kwargs: managed,
    )
    monkeypatch.setattr(
        keyword_relevance_ai_service,
        "select_keyword_review_capability",
        lambda *_args, **_kwargs: CapabilitySelection(
            event_id="event-1",
            connection_id="connection-1",
            model_identifier=private.model_name,
        ),
    )

    def private_attempt(_db, **kwargs):  # noqa: ANN001, ANN202
        response = private.review_keyword_relevance(
            context=kwargs["context"],
            output_schema=GovernedKeywordRelevanceReview.model_json_schema(),
            prompt_template_version="insightos-keyword-relevance-review-v1",
        )
        return keyword_relevance_ai_service._PrivateKeywordReviewResult(
            output=GovernedKeywordRelevanceReview.model_validate(response.payload),
            provider_response=response,
            provider_name=private.name,
            model_name=private.model_name,
            prompt_attempted=True,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            duration_ms=500,
        )

    monkeypatch.setattr(
        keyword_relevance_ai_service,
        "_attempt_private_keyword_review",
        private_attempt,
    )

    payload = keyword_relevance_ai_service.review_uncertain(
        db_session,
        tenant_id=organization.id,
        campaign_id=campaign.id,
        requested_by_user_id=None,
    )

    assert payload["ai_review"]["state"] == "complete"
    assert private.calls == 1
    assert managed.calls == 0
    ai_run = db_session.query(GovernedAIRun).one()
    assert ai_run.provider_name == "private_ai"
    assert ai_run.model_name == "customer-model-v1"
    assert ai_run.estimated_cost == 0
    assert ai_run.reconciled_cost == 0
    assert ai_run.price_card_version is None
    db_session.expire_all()
    assert db_session.get(KeywordResearchSuggestion, suggestions[0].id).relevance_status == "relevant"


def test_private_keyword_review_failure_uses_managed_provider(
    db_session,
    create_test_org,
    monkeypatch,
) -> None:
    organization, campaign, _service, _area, _suggestions = _setup_relevance_case(
        db_session, create_test_org
    )
    managed = FakeRelevanceProvider()
    monkeypatch.setattr(keyword_relevance_ai_service, "get_settings", _private_runtime_settings)
    monkeypatch.setattr(
        keyword_relevance_ai_service,
        "MistralGovernedAIProvider",
        lambda **_kwargs: managed,
    )
    monkeypatch.setattr(
        keyword_relevance_ai_service,
        "select_keyword_review_capability",
        lambda *_args, **_kwargs: CapabilitySelection(
            event_id="event-1",
            connection_id="connection-1",
            model_identifier="customer-model-v1",
        ),
    )
    monkeypatch.setattr(
        keyword_relevance_ai_service,
        "_attempt_private_keyword_review",
        lambda *_args, **_kwargs: keyword_relevance_ai_service._PrivateKeywordReviewResult(
            error_code="ai_output_validation_failed",
            provider_may_have_processed=True,
        ),
    )

    payload = keyword_relevance_ai_service.review_uncertain(
        db_session,
        tenant_id=organization.id,
        campaign_id=campaign.id,
        requested_by_user_id=None,
    )

    assert payload["ai_review"]["state"] == "complete"
    assert managed.calls == 1
    ai_run = db_session.query(GovernedAIRun).one()
    assert ai_run.provider_name == "mistral"
    assert ai_run.reconciled_cost > 0


def test_mistral_relevance_adapter_uses_strict_non_chat_schema() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(request.read() and __import__("json").loads(request.content))
        return httpx.Response(
            200,
            json={
                "id": "request-1",
                "model": "mistral-small-2603",
                "usage": {"prompt_tokens": 20, "completion_tokens": 15},
                "choices": [
                    {
                        "message": {
                            "content": __import__("json").dumps(
                                {
                                    "decisions": [
                                        {
                                            "suggestion_id": "suggestion-1",
                                            "classification": "still_unclear",
                                            "confidence": 0.5,
                                            "matched_service_id": None,
                                            "matched_service_area_id": None,
                                            "area_basis": "unclear",
                                            "reason": "The saved facts do not make the business fit clear.",
                                            "evidence_used": ["search:suggestion-1"],
                                        }
                                    ]
                                }
                            )
                        }
                    }
                ],
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = MistralGovernedAIProvider(
        api_key="test-key",
        endpoint="https://api.mistral.ai/v1/chat/completions",
        model_name="mistral-small-2603",
        timeout_seconds=5,
        max_output_tokens=800,
        max_attempts=1,
        client=client,
    )
    try:
        response = provider.review_keyword_relevance(
            context={"uncertain_searches": [{"suggestion_id": "suggestion-1"}]},
            output_schema={"type": "object", "additionalProperties": False},
            prompt_template_version="insightos-keyword-relevance-review-v1",
        )
    finally:
        client.close()

    assert response.input_tokens == 20
    assert captured["temperature"] == 0
    assert captured["response_format"]["type"] == "json_schema"
    assert captured["response_format"]["json_schema"]["strict"] is True
    assert captured["response_format"]["json_schema"]["name"] == (
        "governed_keyword_relevance_review"
    )
    system_prompt = captured["messages"][0]["content"]
    assert "classification only" in system_prompt
    assert "do not suggest actions" in system_prompt.lower()

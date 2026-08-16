from __future__ import annotations

from datetime import UTC, datetime
import json
from types import SimpleNamespace

import httpx

from app.models.business_location import BusinessLocation
from app.models.competitor import Competitor
from app.models.content import ContentBrief, ContentDraft
from app.models.governed_ai import GovernedAIRun
from app.models.keyword_research import KeywordResearchRun, KeywordResearchSuggestion
from app.services import content_draft_ai_service, content_service
from app.intelligence.contracts.governed_ai import GovernedContentDraftSuggestion
from app.services.governed_ai_provider import (
    GovernedAIProviderResponse,
    MistralGovernedAIProvider,
)
from tests.conftest import create_test_campaign


def _settings(*, configured: bool = True) -> SimpleNamespace:
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


class ContentDraftProvider:
    name = "mistral"
    model_name = "mistral-small-2603"

    def __init__(self, *, invented_evidence: bool = False) -> None:
        self.invented_evidence = invented_evidence
        self.calls = 0
        self.last_context = None

    def suggest_content_draft(
        self,
        *,
        context,
        output_schema,
        prompt_template_version,
    ) -> GovernedAIProviderResponse:
        self.calls += 1
        self.last_context = context
        requested = context["content_draft_request"]
        evidence = context["allowed_evidence_ids"]
        return GovernedAIProviderResponse(
            payload={
                "draft_id": requested["draft_id"],
                "suggestion_state": "ready",
                "suggested_title": "Helpful plumbing services in Reno",
                "sections": [
                    {
                        "order": item["order"],
                        "heading": item["current_heading"],
                        "body": "Learn how our team can help with your plumbing needs.",
                    }
                    for item in requested["requested_sections"]
                ],
                "evidence_used": [
                    "invented_evidence" if self.invented_evidence else evidence[0]
                ],
                "uncertainties": [
                    "Confirm the service details and area before using this wording."
                ],
                "approval_required": True,
                "can_publish": False,
            },
            provider_request_id="content-draft-request",
            model_name=self.model_name,
            input_tokens=700,
            output_tokens=120,
        )


def _accepted_draft(db_session, create_test_org):
    organization = create_test_org(name="Content draft AI org")
    campaign = create_test_campaign(
        db_session,
        organization.id,
        name="Content draft AI campaign",
        domain="content-draft-ai.example",
    )
    now = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)
    location = BusinessLocation(
        organization_id=organization.id,
        name="Reno plumbing",
        domain=campaign.domain,
        status="active",
        created_at=now,
        updated_at=now,
    )
    db_session.add(location)
    db_session.flush()
    campaign.business_location_id = location.id
    run = KeywordResearchRun(
        tenant_id=campaign.tenant_id,
        organization_id=organization.id,
        campaign_id=campaign.id,
        business_location_id=location.id,
        status="complete",
        location_name="Reno",
        sources=["saved_search_evidence"],
        completed_at=now,
    )
    competitor = Competitor(
        tenant_id=campaign.tenant_id,
        campaign_id=campaign.id,
        domain="confirmed-competitor.example",
        discovery_source="manual",
        review_status="confirmed",
    )
    db_session.add_all([run, competitor])
    db_session.flush()
    research = KeywordResearchSuggestion(
        run_id=run.id,
        tenant_id=campaign.tenant_id,
        organization_id=organization.id,
        campaign_id=campaign.id,
        business_location_id=location.id,
        keyword="plumbing services reno",
        normalized_keyword="plumbing services reno",
        source_types=["saved_search_evidence"],
        evidence={},
        intent="service",
        opportunity_group="new_opportunity",
        relevance_score=95,
        relevance_status="relevant",
        opportunity_score=88,
        recommended_action="create_content_brief",
        recommendation_reason="A confirmed competitor appears for this search.",
        source_updated_at=now,
    )
    db_session.add(research)
    db_session.flush()
    brief = ContentBrief(
        tenant_id=campaign.tenant_id,
        organization_id=organization.id,
        campaign_id=campaign.id,
        business_location_id=location.id,
        suggestion_id=research.id,
        competitor_id=competitor.id,
        idempotency_key=f"content-draft-ai:{campaign.id}",
        status="accepted",
        title="Plumbing services in Reno",
        primary_keyword="plumbing services reno",
        recommended_page_action="create_service_page",
        target_url=None,
        competitor_domain=competitor.domain,
        service_name="Plumbing services",
        service_area_name="Reno",
        evidence={"evidence_note": "Saved competitor and customer search evidence."},
        outline=[
            {
                "order": 1,
                "heading": "How we can help",
                "guidance": "Explain the confirmed service clearly.",
            },
            {
                "order": 2,
                "heading": "Where we work",
                "guidance": "Use only the confirmed service area.",
            },
        ],
        created_at=now,
        updated_at=now,
    )
    db_session.add(brief)
    db_session.flush()
    draft = ContentDraft(
        tenant_id=campaign.tenant_id,
        organization_id=organization.id,
        campaign_id=campaign.id,
        business_location_id=location.id,
        content_brief_id=brief.id,
        status="working",
        title="Owner draft title",
        sections=[
            {
                "order": item["order"],
                "heading": item["heading"],
                "guidance": item["guidance"],
                "body": f"OWNER SECRET BODY {item['order']}",
            }
            for item in brief.outline
        ],
        source_brief_hash="a" * 64,
        revision=3,
        automatic_publishing_allowed=False,
        created_at=now,
        updated_at=now,
    )
    db_session.add(draft)
    db_session.commit()
    return campaign, draft


def test_content_draft_suggestion_is_separate_cited_and_idempotent(
    db_session,
    create_test_org,
    monkeypatch,
) -> None:
    monkeypatch.setattr(content_draft_ai_service, "get_settings", _settings)
    campaign, draft = _accepted_draft(db_session, create_test_org)
    original_title = draft.title
    original_sections = list(draft.sections)
    original_revision = draft.revision
    provider = ContentDraftProvider()
    now = datetime(2026, 8, 15, 12, 30, tzinfo=UTC)

    first = content_draft_ai_service.generate_content_draft_suggestion(
        db_session,
        tenant_id=campaign.tenant_id,
        campaign_id=campaign.id,
        draft_id=draft.id,
        requested_by_user_id=None,
        provider=provider,
        now=now,
    )
    replay = content_draft_ai_service.generate_content_draft_suggestion(
        db_session,
        tenant_id=campaign.tenant_id,
        campaign_id=campaign.id,
        draft_id=draft.id,
        requested_by_user_id=None,
        provider=provider,
        now=now,
    )

    db_session.refresh(draft)
    assert first["state"] == "available"
    assert first["suggestion"]["evidence_used"] == ["accepted_content_brief"]
    assert [item["order"] for item in first["suggestion"]["sections"]] == [1, 2]
    assert first["safety"]["owner_draft_changed"] is False
    assert first["safety"]["automatic_publishing_allowed"] is False
    assert replay["idempotent_replay"] is True
    assert provider.calls == 1
    assert "OWNER SECRET BODY" not in str(provider.last_context)
    assert draft.title == original_title
    assert draft.sections == original_sections
    assert draft.revision == original_revision
    assert draft.automatic_publishing_allowed is False

    workspace = content_service.get_content_workspace(
        db_session,
        tenant_id=campaign.tenant_id,
        campaign_id=campaign.id,
    )
    saved = workspace["briefs"][0]["working_draft"]["ai_suggestion"]
    assert saved["state"] == "available"
    assert saved["suggestion"]["suggested_title"] == (
        "Helpful plumbing services in Reno"
    )
    assert "provider" not in str(saved).lower()
    assert "reconciled_cost" not in str(saved)


def test_content_draft_suggestion_rejects_invented_evidence_without_mutation(
    db_session,
    create_test_org,
    monkeypatch,
) -> None:
    monkeypatch.setattr(content_draft_ai_service, "get_settings", _settings)
    campaign, draft = _accepted_draft(db_session, create_test_org)
    original_sections = list(draft.sections)

    result = content_draft_ai_service.generate_content_draft_suggestion(
        db_session,
        tenant_id=campaign.tenant_id,
        campaign_id=campaign.id,
        draft_id=draft.id,
        requested_by_user_id=None,
        provider=ContentDraftProvider(invented_evidence=True),
        now=datetime(2026, 8, 15, 13, 0, tzinfo=UTC),
    )

    db_session.refresh(draft)
    run = (
        db_session.query(GovernedAIRun)
        .filter(
            GovernedAIRun.campaign_id == campaign.id,
            GovernedAIRun.feature == content_draft_ai_service.FEATURE,
        )
        .one()
    )
    assert result["state"] == "invalid_output"
    assert result["suggestion"] is None
    assert run.status == "rejected"
    assert run.error_code == "ai_output_validation_failed"
    assert draft.sections == original_sections
    assert draft.automatic_publishing_allowed is False


def test_mistral_content_suggestion_preserves_server_owned_safety_fields() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content.decode("utf-8")))
        return httpx.Response(
            200,
            json={
                "id": "provider-request",
                "model": "mistral-small-2603",
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "draft_id": "changed-by-provider",
                                    "suggestion_state": "not_enough_information",
                                    "suggested_title": "More details are needed",
                                    "sections": [],
                                    "evidence_used": [],
                                    "uncertainties": ["Confirm the service details."],
                                    "approval_required": False,
                                    "can_publish": True,
                                }
                            )
                        }
                    }
                ],
                "usage": {"prompt_tokens": 20, "completion_tokens": 10},
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = MistralGovernedAIProvider(
        api_key="configured-key",
        endpoint="https://api.mistral.ai/v1/chat/completions",
        model_name="mistral-small-2603",
        timeout_seconds=30,
        max_output_tokens=800,
        max_attempts=1,
        client=client,
    )
    context = {
        "content_draft_request": {
            "draft_id": "draft-owned-by-server",
            "requested_sections": [],
        },
        "allowed_evidence_ids": [],
    }

    response = provider.suggest_content_draft(
        context=context,
        output_schema=GovernedContentDraftSuggestion.model_json_schema(),
        prompt_template_version="content-suggestion-test-v1",
    )

    assert response.payload["draft_id"] == "draft-owned-by-server"
    assert response.payload["approval_required"] is True
    assert response.payload["can_publish"] is False
    assert captured["response_format"]["json_schema"]["strict"] is True
    assert captured["temperature"] == 0
    assert "cannot edit, approve, or publish" in captured["messages"][0]["content"]

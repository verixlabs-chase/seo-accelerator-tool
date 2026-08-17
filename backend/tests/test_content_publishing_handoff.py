from __future__ import annotations

import json
from datetime import UTC, datetime

from app.models.competitor import Competitor
from app.models.content import ContentBrief, ContentDraft
from app.models.intelligence import StrategyRecommendation
from app.models.keyword_research import KeywordResearchRun, KeywordResearchSuggestion
from app.models.recommendation_execution import RecommendationExecution
from app.models.user import User
from app.models.wordpress_change_preview import WordPressChangePreview
from app.services import content_service
from app.services.commercial_plan_service import apply_commercial_plan
from tests.conftest import create_test_campaign


def _login(client) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "a@example.com", "password": "pass-a"},
    )
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


def _ready_new_page_draft(db_session, create_test_org):
    user = db_session.query(User).filter(User.email == "a@example.com").one()
    organization = create_test_org(
        tenant_id=user.tenant_id,
        name="Content Publishing Organization",
    )
    apply_commercial_plan(
        db_session,
        organization_id=organization.id,
        plan_code="multi_location",
    )
    campaign = create_test_campaign(
        db_session,
        organization.id,
        tenant_id=user.tenant_id,
        name="Content Publishing",
        domain="content-publishing.example",
    )
    now = datetime.now(UTC)
    run = KeywordResearchRun(
        tenant_id=user.tenant_id,
        organization_id=organization.id,
        campaign_id=campaign.id,
        status="complete",
        location_name="Reno, Nevada",
        sources=["saved_search_evidence"],
        completed_at=now,
    )
    competitor = Competitor(
        tenant_id=user.tenant_id,
        campaign_id=campaign.id,
        domain="content-competitor.example",
        discovery_source="manual",
        review_status="confirmed",
    )
    db_session.add_all([run, competitor])
    db_session.flush()
    suggestion = KeywordResearchSuggestion(
        run_id=run.id,
        tenant_id=user.tenant_id,
        organization_id=organization.id,
        campaign_id=campaign.id,
        keyword="emergency plumber reno",
        normalized_keyword="emergency plumber reno",
        source_types=["saved_search_evidence"],
        evidence={},
        intent="service",
        opportunity_group="new_opportunity",
        relevance_score=95,
        relevance_status="relevant",
        opportunity_score=88,
        recommended_action="create_content_brief",
        recommendation_reason="A confirmed competitor appears for this saved search.",
        source_updated_at=now,
    )
    db_session.add(suggestion)
    db_session.flush()
    brief = ContentBrief(
        tenant_id=user.tenant_id,
        organization_id=organization.id,
        campaign_id=campaign.id,
        suggestion_id=suggestion.id,
        competitor_id=competitor.id,
        idempotency_key=f"publishing-brief:{campaign.id}",
        status="accepted",
        title="Emergency plumbing in Reno",
        primary_keyword=suggestion.keyword,
        recommended_page_action="create_service_page",
        target_url=None,
        competitor_domain=competitor.domain,
        service_name="Emergency plumbing",
        service_area_name="Reno",
        evidence={"source_updated_at": now.isoformat()},
        outline=[
            {"order": 1, "heading": "Emergency plumbing in Reno", "guidance": "Explain the service."},
            {"order": 2, "heading": "What to expect", "guidance": "Explain the process."},
        ],
        created_at=now,
        updated_at=now,
    )
    db_session.add(brief)
    db_session.flush()
    draft = ContentDraft(
        tenant_id=user.tenant_id,
        organization_id=organization.id,
        campaign_id=campaign.id,
        content_brief_id=brief.id,
        title="Emergency plumbing in Reno",
        sections=[
            {
                "order": 1,
                "heading": "Emergency plumbing in Reno",
                "guidance": "Explain the service.",
                "body": "Emergency plumbing helps Reno homeowners handle urgent leaks and failed fixtures.",
            },
            {
                "order": 2,
                "heading": "What to expect",
                "guidance": "Explain the process.",
                "body": "Call the business to describe the issue and confirm the next available appointment.",
            },
        ],
        source_brief_hash=content_service._content_brief_hash(brief),
        revision=3,
        automatic_publishing_allowed=False,
        created_by_user_id=user.id,
        updated_by_user_id=user.id,
    )
    db_session.add(draft)
    db_session.commit()
    return user, campaign, brief, draft


def test_content_handoff_requires_exact_preview_and_separate_delivery(
    client,
    db_session,
    create_test_org,
) -> None:
    token = _login(client)
    _user, campaign, _brief, draft = _ready_new_page_draft(db_session, create_test_org)
    headers = {"Authorization": f"Bearer {token}"}

    prepared = client.post(
        f"/api/v1/content/drafts/{draft.id}/publishing-handoff",
        json={"campaign_id": campaign.id},
        headers=headers,
    )

    assert prepared.status_code == 200
    prepared_item = prepared.json()["data"]["item"]
    assert prepared_item["state"] == "preview_ready"
    assert prepared_item["target"]["publication_state"] == "draft"
    assert prepared_item["safety"] == {
        "owner_approval_required": True,
        "approval_and_delivery_are_separate": True,
        "automatic_publishing_allowed": False,
        "public_page_requested": False,
        "public_page_changed": False,
    }
    recommendation = db_session.query(StrategyRecommendation).filter_by(
        idempotency_key=content_service._publishing_handoff_key(draft)
    ).one()
    evidence = json.loads(recommendation.evidence_json)
    assert evidence["content_draft_revision"] == 3
    assert evidence["content_blocks"] == [
        {"text": "Emergency plumbing in Reno", "type": "heading"},
        {
            "text": "Emergency plumbing helps Reno homeowners handle urgent leaks and failed fixtures.",
            "type": "paragraph",
        },
        {"text": "What to expect", "type": "heading"},
        {
            "text": "Call the business to describe the issue and confirm the next available appointment.",
            "type": "paragraph",
        },
    ]
    execution = db_session.query(RecommendationExecution).filter_by(
        recommendation_id=recommendation.id
    ).one()
    assert execution.status == "pending"
    preview_row = db_session.query(WordPressChangePreview).filter_by(execution_id=execution.id).one()
    proposed = preview_row.snapshot["changes"][0]["after"]["proposed_value"]
    assert proposed["publication_state"] == "draft"
    assert proposed["content_blocks"] == evidence["content_blocks"]

    missing_acknowledgements = client.post(
        f"/api/v1/content/drafts/{draft.id}/publishing-handoff/approve",
        json={
            "campaign_id": campaign.id,
            "preview_hash": prepared_item["preview"]["preview_hash"],
        },
        headers=headers,
    )
    assert missing_acknowledgements.status_code == 422

    wrong_hash = client.post(
        f"/api/v1/content/drafts/{draft.id}/publishing-handoff/approve",
        json={
            "campaign_id": campaign.id,
            "preview_hash": "0" * 64,
            "reviewed_exact_preview": True,
            "understands_wordpress_draft": True,
            "understands_not_public": True,
        },
        headers=headers,
    )
    assert wrong_hash.status_code == 409

    preview_hash = prepared_item["preview"]["preview_hash"]
    approved = client.post(
        f"/api/v1/content/drafts/{draft.id}/publishing-handoff/approve",
        json={
            "campaign_id": campaign.id,
            "preview_hash": preview_hash,
            "reviewed_exact_preview": True,
            "understands_wordpress_draft": True,
            "understands_not_public": True,
        },
        headers=headers,
    )
    assert approved.status_code == 200
    assert approved.json()["data"]["item"]["state"] == "approved"
    assert db_session.get(RecommendationExecution, execution.id).status == "scheduled"

    delivered = client.post(
        f"/api/v1/content/drafts/{draft.id}/publishing-handoff/deliver",
        json={
            "campaign_id": campaign.id,
            "preview_hash": preview_hash,
            "create_non_public_draft": True,
        },
        headers=headers,
    )
    assert delivered.status_code == 200
    delivered_item = delivered.json()["data"]["item"]
    assert delivered_item["state"] == "draft_created"
    assert delivered_item["delivery"]["non_public_wordpress_draft_created"] is True
    assert delivered_item["safety"]["public_page_requested"] is False


def test_existing_page_draft_cannot_use_new_page_handoff(
    client,
    db_session,
    create_test_org,
) -> None:
    token = _login(client)
    _user, campaign, brief, draft = _ready_new_page_draft(db_session, create_test_org)
    brief.recommended_page_action = "improve_existing_page"
    brief.target_url = "https://content-publishing.example/existing"
    draft.source_brief_hash = content_service._content_brief_hash(brief)
    db_session.commit()

    response = client.post(
        f"/api/v1/content/drafts/{draft.id}/publishing-handoff",
        json={"campaign_id": campaign.id},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 409
    assert db_session.query(RecommendationExecution).count() == 0

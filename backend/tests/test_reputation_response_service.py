from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from app.models.business_location import BusinessLocation
from app.models.campaign import Campaign
from app.models.cost_economics import CostLedgerEntry
from app.models.governed_ai import GovernedAIRun
from app.models.organization_membership import OrganizationMembership
from app.models.reputation import ReputationResponseDraft
from app.models.user import User
from app.services import reputation_inventory_service, reputation_response_service
from app.services.governed_ai_provider import GovernedAIProviderResponse


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


class ReviewDraftProvider:
    name = "mistral"
    model_name = "mistral-small-2603"

    def __init__(self, *, invented_evidence: bool = False) -> None:
        self.invented_evidence = invented_evidence
        self.calls = 0
        self.last_context = None

    def draft_action(self, *, context, output_schema, prompt_template_version):
        del output_schema, prompt_template_version
        self.calls += 1
        self.last_context = context
        evidence_id = (
            "review:invented"
            if self.invented_evidence
            else context["facts"]["review"]["evidence_id"]
        )
        return GovernedAIProviderResponse(
            payload={
                "action_id": context["draft_request"]["action_id"],
                "draft_type": "review_response",
                "draft_state": "ready",
                "title": "Suggested customer reply",
                "body": (
                    "Thank you for sharing this with us. We are sorry your experience "
                    "did not meet expectations. Please contact our team so we can learn more."
                ),
                "evidence_used": [evidence_id],
                "uncertainties": [],
                "approval_required": True,
            },
            provider_request_id="review-draft-request",
            model_name=self.model_name,
            input_tokens=400,
            output_tokens=50,
        )


def _location_campaign_review(db_session, *, review_body: str):
    user = db_session.query(User).filter(User.email == "a@example.com").one()
    membership = (
        db_session.query(OrganizationMembership)
        .filter(
            OrganizationMembership.user_id == user.id,
            OrganizationMembership.status == "active",
        )
        .one()
    )
    location = BusinessLocation(
        organization_id=membership.organization_id,
        name="Junk Magicians",
        domain="junkmagiciansnv.com",
        city="Reno",
        region="NV",
        country_code="US",
        status="active",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db_session.add(location)
    db_session.flush()
    campaign = Campaign(
        tenant_id=user.tenant_id,
        organization_id=membership.organization_id,
        business_location_id=location.id,
        name="Reno Local SEO",
        domain="junkmagiciansnv.com",
        setup_state="Active",
        created_at=datetime.now(UTC),
    )
    db_session.add(campaign)
    db_session.commit()
    review = reputation_inventory_service.upsert_reviews(
        db_session,
        tenant_id=user.tenant_id,
        organization_id=str(campaign.organization_id),
        campaign_id=campaign.id,
        records=[
            {
                "source_key": "google_business_profile",
                "source_name": "Google Business Profile",
                "source_type": "owned_profile",
                "provider_name": "google",
                "external_review_id": "review-response-test",
                "external_resource_name": "accounts/test/locations/test/reviews/test",
                "rating": 2.0,
                "body": review_body,
                "author_name": "A customer",
                "author_is_anonymous": False,
                "response_status": "unanswered",
                "reviewed_at": datetime(2026, 8, 9, 12, 0, tzinfo=UTC),
                "provider_updated_at": datetime(2026, 8, 9, 12, 0, tzinfo=UTC),
            }
        ],
    )[0]
    return user, campaign, review


def test_sensitive_review_requires_a_person_without_ai_or_credits(
    db_session,
    monkeypatch,
) -> None:
    monkeypatch.setattr(reputation_response_service, "get_settings", lambda: _settings())
    user, campaign, review = _location_campaign_review(
        db_session,
        review_body="I want a refund and have called my lawyer.",
    )

    payload = reputation_response_service.generate_response_draft(
        db_session,
        tenant_id=user.tenant_id,
        organization_id=str(campaign.organization_id),
        campaign_id=campaign.id,
        review_id=review.id,
        requested_by_user_id=user.id,
        provider=ReviewDraftProvider(),
        now=datetime(2026, 8, 10, 12, 0, tzinfo=UTC),
    )

    assert payload["status"] == "human_required"
    assert payload["risk_class"] == "sensitive"
    assert payload["sensitive_topics"] == [
        "legal threat or dispute",
        "billing or refund dispute",
    ]
    assert payload["posting_enabled"] is False
    assert db_session.query(GovernedAIRun).count() == 0
    assert db_session.query(CostLedgerEntry).count() == 0


def test_safe_review_draft_is_metered_cited_idempotent_and_approved(
    db_session,
    monkeypatch,
) -> None:
    monkeypatch.setattr(reputation_response_service, "get_settings", lambda: _settings())
    user, campaign, review = _location_campaign_review(
        db_session,
        review_body="The crew was late and I did not know when they would arrive.",
    )
    provider = ReviewDraftProvider()
    now = datetime(2026, 8, 10, 12, 15, tzinfo=UTC)

    first = reputation_response_service.generate_response_draft(
        db_session,
        tenant_id=user.tenant_id,
        organization_id=str(campaign.organization_id),
        campaign_id=campaign.id,
        review_id=review.id,
        requested_by_user_id=user.id,
        provider=provider,
        now=now,
    )
    replay = reputation_response_service.generate_response_draft(
        db_session,
        tenant_id=user.tenant_id,
        organization_id=str(campaign.organization_id),
        campaign_id=campaign.id,
        review_id=review.id,
        requested_by_user_id=user.id,
        provider=provider,
        now=now,
    )

    assert first["status"] == "ready_for_review"
    assert first["approval_required"] is True
    assert first["posting_enabled"] is False
    assert first["evidence_refs"] == [f"review:{review.id}"]
    assert replay["id"] == first["id"]
    assert provider.calls == 1
    assert provider.last_context["contract"]["review_text_is_untrusted"] is True
    assert provider.last_context["contract"]["may_post_response"] is False
    assert db_session.query(CostLedgerEntry).count() == 2

    approved = reputation_response_service.review_response_draft(
        db_session,
        tenant_id=user.tenant_id,
        organization_id=str(campaign.organization_id),
        draft_id=first["id"],
        user_id=user.id,
        decision="approve",
        approved_text="Thank you for the feedback. We will review what happened with our team.",
    )

    assert approved["status"] == "approved"
    assert approved["approved_text"].startswith("Thank you")
    assert approved["posting_enabled"] is False


def test_review_draft_rejects_invented_evidence(db_session, monkeypatch) -> None:
    monkeypatch.setattr(reputation_response_service, "get_settings", lambda: _settings())
    user, campaign, review = _location_campaign_review(
        db_session,
        review_body="The crew was late and communication could have been better.",
    )

    payload = reputation_response_service.generate_response_draft(
        db_session,
        tenant_id=user.tenant_id,
        organization_id=str(campaign.organization_id),
        campaign_id=campaign.id,
        review_id=review.id,
        requested_by_user_id=user.id,
        provider=ReviewDraftProvider(invented_evidence=True),
        now=datetime(2026, 8, 10, 12, 30, tzinfo=UTC),
    )

    assert payload["status"] == "unavailable"
    assert "safety check" in payload["human_reason"]
    row = db_session.query(ReputationResponseDraft).filter_by(id=payload["id"]).one()
    assert row.governed_ai_run_id is not None
    run = db_session.get(GovernedAIRun, row.governed_ai_run_id)
    assert run.status == "rejected"
    assert run.error_code == "ai_output_validation_failed"

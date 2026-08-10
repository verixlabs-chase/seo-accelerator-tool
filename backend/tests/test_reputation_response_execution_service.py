from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import HTTPException

from app.models.business_location import BusinessLocation
from app.models.campaign import Campaign
from app.models.data_connection import DataConnection
from app.models.organization_membership import OrganizationMembership
from app.models.platform_job import PlatformJob
from app.models.reputation import (
    ReputationResponseDraft,
    ReputationResponseExecution,
    ReputationResponsePolicy,
)
from app.models.user import User
from app.providers.google_reviews import GoogleReviewsProviderError
from app.services import (
    durable_job_service,
    reputation_inventory_service,
    reputation_response_execution_service,
)


def _approved_reply_context(db_session):
    user = db_session.query(User).filter(User.email == "a@example.com").one()
    membership = (
        db_session.query(OrganizationMembership)
        .filter(
            OrganizationMembership.user_id == user.id,
            OrganizationMembership.status == "active",
        )
        .one()
    )
    now = datetime(2026, 8, 10, 18, 0, tzinfo=UTC)
    location = BusinessLocation(
        organization_id=membership.organization_id,
        name="Junk Magicians",
        domain="junkmagiciansnv.com",
        city="Reno",
        region="NV",
        country_code="US",
        status="active",
        created_at=now,
        updated_at=now,
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
        created_at=now,
    )
    db_session.add(campaign)
    db_session.flush()
    connection = DataConnection(
        tenant_id=user.tenant_id,
        organization_id=membership.organization_id,
        business_location_id=location.id,
        campaign_id=campaign.id,
        provider_name="google_business_profile",
        external_resource_id="locations/456",
        external_resource_name="Junk Magicians",
        resource_scope="owned_business_profile",
        status="connected",
        sync_cursor={},
        connection_metadata={"account_id": "accounts/123"},
        created_by_user_id=user.id,
        created_at=now,
        updated_at=now,
    )
    db_session.add(connection)
    db_session.commit()
    review = reputation_inventory_service.upsert_reviews(
        db_session,
        tenant_id=user.tenant_id,
        organization_id=str(membership.organization_id),
        campaign_id=campaign.id,
        records=[
            {
                "source_key": "google_business_profile",
                "source_name": "Google Business Profile",
                "source_type": "owned_profile",
                "provider_name": "google",
                "external_review_id": "review-1",
                "external_resource_name": "accounts/123/locations/456/reviews/review-1",
                "rating": 4,
                "body": "The team was helpful.",
                "author_name": "A customer",
                "author_is_anonymous": False,
                "response_status": "unanswered",
                "reviewed_at": now,
                "provider_updated_at": now,
            }
        ],
    )[0]
    policy = ReputationResponsePolicy(
        tenant_id=user.tenant_id,
        organization_id=membership.organization_id,
        version="review-response-policy-test",
        status="active",
        mode="draft_only",
        rules={},
        rules_hash="a" * 64,
        created_by_user_id=user.id,
        created_at=now,
        updated_at=now,
    )
    db_session.add(policy)
    db_session.flush()
    approved_text = "Thank you for taking the time to share this with us."
    draft = ReputationResponseDraft(
        tenant_id=user.tenant_id,
        organization_id=membership.organization_id,
        campaign_id=campaign.id,
        business_location_id=location.id,
        review_id=review.id,
        policy_id=policy.id,
        idempotency_key=f"approved:{review.id}",
        status="approved",
        risk_class="standard",
        sensitive_topics=[],
        policy_version=policy.version,
        policy_snapshot={},
        review_snapshot={},
        evidence_refs=[f"review:{review.id}"],
        draft_text=approved_text,
        approved_text=approved_text,
        reviewed_by_user_id=user.id,
        reviewed_at=now,
        created_at=now,
        updated_at=now,
    )
    db_session.add(draft)
    db_session.commit()
    return user, campaign, connection, review, draft


def _authorize(db_session, user, campaign, connection):
    return reputation_response_execution_service.authorize_validation(
        db_session,
        organization_id=str(campaign.organization_id),
        connection_id=connection.id,
        authorized_by_user_id=user.id,
        proof_reference="google-approval-case-12345",
    )


def _queue(db_session, user, campaign, draft):
    return reputation_response_execution_service.queue_execution(
        db_session,
        tenant_id=user.tenant_id,
        organization_id=str(campaign.organization_id),
        campaign_id=campaign.id,
        draft_id=draft.id,
        requested_by_user_id=user.id,
        confirmation_version=reputation_response_execution_service.CONFIRMATION_VERSION,
        confirm_publish_to_google=True,
    )


def test_publish_requires_capability_and_explicit_confirmation(db_session):
    user, campaign, connection, _review, draft = _approved_reply_context(db_session)

    with pytest.raises(HTTPException) as capability_error:
        _queue(db_session, user, campaign, draft)
    assert capability_error.value.detail["reason_code"] == "review_reply_capability_not_authorized"

    _authorize(db_session, user, campaign, connection)
    with pytest.raises(HTTPException) as confirmation_error:
        reputation_response_execution_service.queue_execution(
            db_session,
            tenant_id=user.tenant_id,
            organization_id=str(campaign.organization_id),
            campaign_id=campaign.id,
            draft_id=draft.id,
            requested_by_user_id=user.id,
            confirmation_version=reputation_response_execution_service.CONFIRMATION_VERSION,
            confirm_publish_to_google=False,
        )
    assert confirmation_error.value.detail["reason_code"] == "review_reply_publish_confirmation_required"


def test_approved_reply_is_queued_idempotently_and_provider_receipt_is_saved(db_session):
    user, campaign, connection, review, draft = _approved_reply_context(db_session)
    capability = _authorize(db_session, user, campaign, connection)
    first = _queue(db_session, user, campaign, draft)
    replay = _queue(db_session, user, campaign, draft)

    assert replay.id == first.id
    assert first.status == "queued"
    assert first.platform_job_id
    assert db_session.query(ReputationResponseExecution).count() == 1
    assert db_session.query(PlatformJob).filter_by(id=first.platform_job_id).one().job_type == (
        reputation_response_execution_service.JOB_TYPE
    )
    assert (
        durable_job_service.DEFAULT_HANDLERS[reputation_response_execution_service.JOB_TYPE]
        is not None
    )

    class FakeProvider:
        def update_reply(self, *, review_name, comment):
            assert review_name == "accounts/123/locations/456/reviews/review-1"
            assert comment == draft.approved_text
            return {
                "comment": comment,
                "update_time": datetime(2026, 8, 10, 19, 0, tzinfo=UTC),
                "reply_state": "PUBLISHED",
                "policy_violation": None,
            }

    result = reputation_response_execution_service.dispatch_execution(
        db_session,
        execution_id=first.id,
        provider=FakeProvider(),
    )
    db_session.commit()
    db_session.refresh(first)
    db_session.refresh(review)
    db_session.refresh(capability)

    assert result["status"] == "posted"
    assert first.status == "posted"
    assert first.provider_receipt["reply_state"] == "PUBLISHED"
    assert first.provider_receipt["comment_hash"] == first.approved_text_hash
    assert review.response_status == "responded"
    assert review.response_text == draft.approved_text
    assert capability.status == "verified"


def test_retryable_provider_failure_is_recorded_without_changing_approval(db_session):
    user, campaign, connection, _review, draft = _approved_reply_context(db_session)
    _authorize(db_session, user, campaign, connection)
    execution = _queue(db_session, user, campaign, draft)

    error = GoogleReviewsProviderError(
        "Google review replies are temporarily busy.",
        reason_code="review_reply_temporarily_unavailable",
        retryable=True,
        status_code=503,
    )

    class FailingProvider:
        def update_reply(self, **_kwargs):
            raise error

    with pytest.raises(GoogleReviewsProviderError):
        reputation_response_execution_service.dispatch_execution(
            db_session,
            execution_id=execution.id,
            provider=FailingProvider(),
        )
    db_session.rollback()
    reputation_response_execution_service.record_dispatch_failure(
        db_session,
        execution_id=execution.id,
        error=error,
    )
    db_session.commit()
    db_session.refresh(execution)

    assert execution.status == "retrying"
    assert execution.error_code == "review_reply_temporarily_unavailable"
    assert execution.approved_text == draft.approved_text
    assert execution.attempt_count == 1


def test_access_denial_blocks_execution_and_revokes_capability(db_session):
    user, campaign, connection, _review, draft = _approved_reply_context(db_session)
    capability = _authorize(db_session, user, campaign, connection)
    execution = _queue(db_session, user, campaign, draft)

    class DeniedProvider:
        def update_reply(self, **_kwargs):
            raise GoogleReviewsProviderError(
                "Google review-reply access needs attention.",
                reason_code="review_reply_access_denied",
                retryable=False,
                status_code=403,
            )

    result = reputation_response_execution_service.dispatch_execution(
        db_session,
        execution_id=execution.id,
        provider=DeniedProvider(),
    )
    db_session.commit()
    db_session.refresh(execution)
    db_session.refresh(capability)

    assert result["status"] == "blocked"
    assert execution.status == "blocked"
    assert capability.status == "revoked"
    assert capability.last_failure_code == "review_reply_access_denied"


def test_customer_can_pause_resume_and_cancel_before_dispatch(db_session):
    user, campaign, connection, _review, draft = _approved_reply_context(db_session)
    _authorize(db_session, user, campaign, connection)
    execution = _queue(db_session, user, campaign, draft)

    paused = reputation_response_execution_service.control_execution(
        db_session,
        tenant_id=user.tenant_id,
        organization_id=str(campaign.organization_id),
        execution_id=execution.id,
        action="pause",
    )
    assert paused.status == "paused"

    resumed = reputation_response_execution_service.control_execution(
        db_session,
        tenant_id=user.tenant_id,
        organization_id=str(campaign.organization_id),
        execution_id=execution.id,
        action="resume",
    )
    assert resumed.status == "queued"

    cancelled = reputation_response_execution_service.control_execution(
        db_session,
        tenant_id=user.tenant_id,
        organization_id=str(campaign.organization_id),
        execution_id=execution.id,
        action="cancel",
    )
    job = db_session.get(PlatformJob, execution.platform_job_id)
    assert cancelled.status == "cancelled"
    assert job.status == "failed"


def test_changed_review_blocks_without_calling_provider(db_session):
    user, campaign, connection, review, draft = _approved_reply_context(db_session)
    _authorize(db_session, user, campaign, connection)
    execution = _queue(db_session, user, campaign, draft)
    review.response_status = "responded"
    review.response_text = "A reply appeared elsewhere."
    db_session.commit()

    class UnexpectedProvider:
        def update_reply(self, **_kwargs):
            raise AssertionError("A changed review must fail before the provider call.")

    result = reputation_response_execution_service.dispatch_execution(
        db_session,
        execution_id=execution.id,
        provider=UnexpectedProvider(),
    )
    db_session.commit()
    db_session.refresh(execution)

    assert result["status"] == "blocked"
    assert execution.error_code == "review_changed_before_publish"

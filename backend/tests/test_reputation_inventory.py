from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json

from app.models.business_location import BusinessLocation
from app.models.campaign import Campaign
from app.models.data_connection import DataConnection
from app.models.organization_membership import OrganizationMembership
from app.models.reputation import ReputationReviewObservation
from app.events.outbox.event_outbox import EventOutbox
from app.models.user import User
from app.services import durable_job_service, reputation_inventory_service


def _location_campaign(db_session) -> tuple[User, Campaign, BusinessLocation]:
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
    return user, campaign, location


def _review(**overrides):
    record = {
        "source_key": "google_business_profile",
        "source_name": "Google Business Profile",
        "source_type": "owned_profile",
        "provider_name": "google",
        "external_review_id": "review-1",
        "external_resource_name": "accounts/123/locations/456/reviews/review-1",
        "rating": 2.0,
        "body": "The crew arrived late.",
        "author_name": "A customer",
        "author_is_anonymous": False,
        "response_status": "unanswered",
        "reviewed_at": datetime(2026, 8, 1, 12, 0, tzinfo=UTC),
        "provider_updated_at": datetime(2026, 8, 1, 12, 0, tzinfo=UTC),
    }
    record.update(overrides)
    return record


def test_reputation_inventory_keeps_response_history_and_scope(db_session):
    user, campaign, location = _location_campaign(db_session)
    first_time = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)
    first = reputation_inventory_service.upsert_reviews(
        db_session,
        tenant_id=user.tenant_id,
        organization_id=str(campaign.organization_id),
        campaign_id=campaign.id,
        records=[_review()],
        captured_at=first_time,
    )[0]
    second = reputation_inventory_service.upsert_reviews(
        db_session,
        tenant_id=user.tenant_id,
        organization_id=str(campaign.organization_id),
        campaign_id=campaign.id,
        records=[
            _review(
                response_status="responded",
                response_text="We are sorry about the delay and appreciate the feedback.",
                response_updated_at=first_time + timedelta(hours=2),
            )
        ],
        captured_at=first_time + timedelta(days=1),
    )[0]

    assert first.id == second.id
    assert second.business_location_id == location.id
    assert second.response_status == "responded"
    observations = (
        db_session.query(ReputationReviewObservation)
        .filter(ReputationReviewObservation.review_id == first.id)
        .order_by(ReputationReviewObservation.captured_at)
        .all()
    )
    assert [item.snapshot["response_status"] for item in observations] == [
        "unanswered",
        "responded",
    ]
    saved_events = (
        db_session.query(EventOutbox)
        .filter(EventOutbox.event_type == "reputation.review.saved")
        .order_by(EventOutbox.created_at)
        .all()
    )
    assert len(saved_events) == 2
    assert all(
        json.loads(item.payload_json)["payload"]["review_id"] == first.id
        for item in saved_events
    )
    reputation_inventory_service.upsert_reviews(
        db_session,
        tenant_id=user.tenant_id,
        organization_id=str(campaign.organization_id),
        campaign_id=campaign.id,
        records=[
            _review(
                response_status="responded",
                response_text="We are sorry about the delay and appreciate the feedback.",
                response_updated_at=first_time + timedelta(hours=2),
            )
        ],
        captured_at=first_time + timedelta(days=2),
    )
    assert (
        db_session.query(EventOutbox)
        .filter(EventOutbox.event_type == "reputation.review.saved")
        .count()
        == 2
    )


def test_reputation_inventory_filters_and_summarizes(db_session):
    user, campaign, _location = _location_campaign(db_session)
    reputation_inventory_service.upsert_reviews(
        db_session,
        tenant_id=user.tenant_id,
        organization_id=str(campaign.organization_id),
        campaign_id=campaign.id,
        records=[
            _review(),
            _review(
                external_review_id="review-2",
                rating=5,
                body="Great service.",
                response_status="responded",
                response_text="Thank you!",
            ),
        ],
    )

    unanswered = reputation_inventory_service.list_reviews(
        db_session,
        tenant_id=user.tenant_id,
        organization_id=str(campaign.organization_id),
        campaign_id=campaign.id,
        response_status="unanswered",
    )
    all_rows = reputation_inventory_service.list_reviews(
        db_session,
        tenant_id=user.tenant_id,
        organization_id=str(campaign.organization_id),
        campaign_id=campaign.id,
    )
    summary = reputation_inventory_service.inventory_summary(all_rows)

    assert [row.external_review_id for row in unanswered] == ["review-1"]
    assert summary == {
        "total": 2,
        "unanswered": 1,
        "responded": 1,
        "rating_three_or_lower": 1,
        "average_rating": 3.5,
        "newest_observation_at": max(row.last_seen_at for row in all_rows),
    }


def test_reputation_inventory_api_is_read_only_and_hides_internal_provider(
    client,
    db_session,
):
    user, campaign, _location = _location_campaign(db_session)
    reputation_inventory_service.upsert_reviews(
        db_session,
        tenant_id=user.tenant_id,
        organization_id=str(campaign.organization_id),
        campaign_id=campaign.id,
        records=[_review()],
    )
    login = client.post("/api/v1/auth/login", json={"email": "a@example.com", "password": "pass-a"})
    token = login.json()["data"]["access_token"]
    response = client.get(
        f"/api/v1/reviews/inventory?campaign_id={campaign.id}&response_status=unanswered",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["summary"]["unanswered"] == 1
    assert data["items"][0]["source_name"] == "Google Business Profile"
    assert "provider_name" not in data["items"][0]
    assert data["truth"]["direct_reply_available"] is False
    assert data["truth"]["ai_reply_available"] is True
    assert "connect this location" in data["truth"]["direct_reply_reason"].lower()
    assert "provider_name" not in str(data).lower()


def test_owned_review_sync_is_paginated_location_scoped_and_read_only(
    db_session,
    monkeypatch,
):
    user, campaign, location = _location_campaign(db_session)
    connection = DataConnection(
        tenant_id=user.tenant_id,
        organization_id=str(campaign.organization_id),
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
    )
    db_session.add(connection)
    db_session.commit()

    calls: list[tuple[str, str | None]] = []

    class FakeReviewsProvider:
        def __init__(self, **_kwargs):
            pass

        def list_reviews(self, *, parent, page_size, page_token=None):
            assert page_size == 50
            calls.append((parent, page_token))
            if page_token is None:
                return {
                    "items": [_review()],
                    "average_rating": 3.5,
                    "total_review_count": 2,
                    "next_page_token": "page-2",
                }
            return {
                "items": [
                    _review(
                        external_review_id="review-2",
                        rating=5,
                        body="Fast and professional.",
                    )
                ],
                "average_rating": 3.5,
                "total_review_count": 2,
                "next_page_token": None,
            }

    monkeypatch.setattr(
        reputation_inventory_service,
        "GoogleBusinessProfileReviewsProvider",
        FakeReviewsProvider,
    )
    monkeypatch.setattr(
        reputation_inventory_service,
        "_google_access_token",
        lambda _db, _organization_id: "access-token",
    )

    result = reputation_inventory_service.sync_owned_profile_reviews(
        db_session,
        connection=connection,
    )

    assert calls == [
        ("accounts/123/locations/456", None),
        ("accounts/123/locations/456", "page-2"),
    ]
    assert result["reviews_saved"] == 2
    assert result["reply_mutations_enabled"] is False
    assert connection.sync_cursor["owned_reviews"]["pages_received"] == 2
    assert connection.connection_metadata["owned_reviews"]["reply_mutations_enabled"] is False


def test_owned_review_sync_job_is_hourly_idempotent(db_session):
    user, campaign, location = _location_campaign(db_session)
    connection = DataConnection(
        tenant_id=user.tenant_id,
        organization_id=str(campaign.organization_id),
        business_location_id=location.id,
        campaign_id=campaign.id,
        provider_name="google_business_profile",
        external_resource_id="locations/456",
        resource_scope="owned_business_profile",
        status="connected",
        sync_cursor={},
        connection_metadata={"account_id": "accounts/123"},
    )
    db_session.add(connection)
    db_session.flush()
    first = durable_job_service.create_owned_review_sync_job(
        db_session,
        connection=connection,
        now=datetime(2026, 8, 10, 12, 5, tzinfo=UTC),
    )
    db_session.flush()
    second = durable_job_service.create_owned_review_sync_job(
        db_session,
        connection=connection,
        now=datetime(2026, 8, 10, 12, 55, tzinfo=UTC),
    )

    assert first.id == second.id
    assert first.job_type == durable_job_service.OWNED_REVIEW_SYNC_JOB_TYPE
    assert durable_job_service.DEFAULT_HANDLERS[first.job_type]


def test_review_sync_requires_an_owned_profile_connection(client, db_session):
    _user, campaign, _location = _location_campaign(db_session)
    login = client.post("/api/v1/auth/login", json={"email": "a@example.com", "password": "pass-a"})
    token = login.json()["data"]["access_token"]
    response = client.post(
        f"/api/v1/reviews/sync?campaign_id={campaign.id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 409
    assert (
        response.json()["errors"][0]["details"]["reason_code"]
        == "owned_profile_connection_required"
    )

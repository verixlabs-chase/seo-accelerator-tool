from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.models.business_location import BusinessLocation
from app.models.campaign import Campaign
from app.models.organization_membership import OrganizationMembership
from app.models.reputation import ReputationReviewObservation
from app.models.user import User
from app.services import reputation_inventory_service


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
    assert data["truth"]["ai_reply_available"] is False
    assert "provider_name" not in str(data).lower()

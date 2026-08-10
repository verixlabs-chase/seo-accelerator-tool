from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.models.business_location import BusinessLocation
from app.models.campaign import Campaign
from app.models.organization_membership import OrganizationMembership
from app.models.user import User
from app.services import reputation_intelligence_service, reputation_inventory_service


NOW = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)


def _campaign(db_session, *, name: str, city: str) -> tuple[User, Campaign]:
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
        name=name,
        domain=f"{name.lower().replace(' ', '')}.example",
        city=city,
        region="NV",
        country_code="US",
        status="active",
        created_at=NOW,
        updated_at=NOW,
    )
    db_session.add(location)
    db_session.flush()
    campaign = Campaign(
        tenant_id=user.tenant_id,
        organization_id=membership.organization_id,
        business_location_id=location.id,
        name=f"{name} SEO",
        domain=location.domain,
        setup_state="Active",
        created_at=NOW,
    )
    db_session.add(campaign)
    db_session.commit()
    return user, campaign


def _save_reviews(db_session, user: User, campaign: Campaign, rows: list[dict]) -> None:
    records = []
    for index, row in enumerate(rows, start=1):
        reviewed_at = row.get("reviewed_at", NOW - timedelta(days=index))
        response_status = row.get("response_status", "unanswered")
        records.append(
            {
                "source_key": "google_business_profile",
                "source_name": "Google Business Profile",
                "source_type": "owned_profile",
                "provider_name": "google",
                "external_review_id": f"{campaign.id}-review-{index}",
                "external_resource_name": f"accounts/1/locations/1/reviews/{index}",
                "rating": row.get("rating", 5),
                "body": row.get("body", "Great service."),
                "author_name": f"Customer {index}",
                "author_is_anonymous": False,
                "response_status": response_status,
                "response_text": "Thank you." if response_status == "responded" else None,
                "response_updated_at": row.get("response_updated_at"),
                "reviewed_at": reviewed_at,
                "provider_updated_at": reviewed_at,
            }
        )
    reputation_inventory_service.upsert_reviews(
        db_session,
        tenant_id=user.tenant_id,
        organization_id=str(campaign.organization_id),
        campaign_id=campaign.id,
        records=records,
        captured_at=NOW,
    )


def test_location_intelligence_uses_equal_periods_and_cites_review_evidence(db_session):
    user, campaign = _campaign(db_session, name="Reno", city="Reno")
    _save_reviews(
        db_session,
        user,
        campaign,
        [
            {
                "rating": 1,
                "body": "The crew arrived late and communication was poor.",
                "reviewed_at": NOW - timedelta(days=2),
            },
            {
                "rating": 2,
                "body": "The appointment was late and the crew was rude.",
                "reviewed_at": NOW - timedelta(days=8),
            },
            {
                "rating": 5,
                "body": "The crew was friendly and quick.",
                "response_status": "responded",
                "reviewed_at": NOW - timedelta(days=15),
                "response_updated_at": NOW - timedelta(days=12),
            },
            {
                "rating": 5,
                "body": "Professional work.",
                "response_status": "responded",
                "reviewed_at": NOW - timedelta(days=16),
                "response_updated_at": NOW - timedelta(days=15),
            },
            {
                "rating": 5,
                "body": "Great service.",
                "reviewed_at": NOW - timedelta(days=35),
            },
            {
                "rating": 4,
                "body": "Good service.",
                "reviewed_at": NOW - timedelta(days=45),
            },
            {
                "rating": 5,
                "body": "Good service.",
                "reviewed_at": NOW - timedelta(days=55),
            },
        ],
    )

    result = reputation_intelligence_service.location_intelligence(
        db_session,
        tenant_id=user.tenant_id,
        organization_id=str(campaign.organization_id),
        campaign_id=campaign.id,
        now=NOW,
    )

    metrics = result["metrics"]
    assert metrics["reviews_last_30_days"] == 4
    assert metrics["reviews_previous_30_days"] == 3
    assert metrics["review_pace_change"] == 1
    assert metrics["answerable_reviews"] == 7
    assert metrics["responded_reviews"] == 2
    assert metrics["response_rate_percent"] == 28.6
    assert metrics["median_response_hours"] == 48
    assert metrics["response_time_sample_size"] == 2
    arrival = next(item for item in result["themes"] if item["key"] == "arrival")
    assert arrival["negative_mentions"] == 2
    assert len(arrival["evidence_review_ids"]) == 2
    theme_action = next(item for item in result["actions"] if item["id"] == "review_theme_arrival")
    assert theme_action["current_value"] == 2
    assert theme_action["target_value"] == 0
    assert theme_action["evidence_review_ids"] == arrival["evidence_review_ids"]
    assert len(result["weekly_trend"]) == 12
    assert result["evidence"]["claims_limited_to_saved_reviews"] is True


def test_portfolio_intelligence_aggregates_counts_and_flags_real_outliers(db_session):
    user, strong = _campaign(db_session, name="Reno", city="Reno")
    _save_reviews(
        db_session,
        user,
        strong,
        [
            {
                "rating": 5,
                "response_status": "responded",
                "response_updated_at": NOW - timedelta(hours=12),
            },
            {
                "rating": 5,
                "response_status": "responded",
                "response_updated_at": NOW - timedelta(hours=6),
            },
            {"rating": 5, "response_status": "unanswered"},
            {"rating": 4, "response_status": "unanswered"},
            {"rating": 5, "response_status": "unanswered"},
        ],
    )
    _other_user, weak = _campaign(db_session, name="Sparks", city="Sparks")
    _save_reviews(
        db_session,
        user,
        weak,
        [
            {"rating": 2, "body": "Late appointment."},
            {"rating": 2, "body": "Late crew."},
            {"rating": 3, "body": "Slow service."},
        ],
    )

    result = reputation_intelligence_service.portfolio_intelligence(
        db_session,
        tenant_id=user.tenant_id,
        organization_id=str(strong.organization_id),
        now=NOW,
    )

    assert result["summary"]["locations"] == 2
    assert result["summary"]["total_reviews"] == 8
    assert result["summary"]["unanswered_reviews"] == 6
    assert result["summary"]["response_rate_percent"] == 25
    sparks = next(item for item in result["locations"] if item["location_name"] == "Sparks")
    codes = {item["code"] for item in sparks["outliers"]}
    assert "rating_below_portfolio" in codes
    assert sparks["attention_score"] > 0
    assert result["locations"][0]["attention_score"] >= result["locations"][1]["attention_score"]


def test_review_intelligence_endpoints_are_plain_language_and_scoped(client, db_session):
    user, first = _campaign(db_session, name="Reno", city="Reno")
    _save_reviews(db_session, user, first, [{"rating": 5}])
    _other_user, second = _campaign(db_session, name="Sparks", city="Sparks")
    _save_reviews(db_session, user, second, [{"rating": 2}])
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "a@example.com", "password": "pass-a"},
    )
    token = login.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    location_response = client.get(
        f"/api/v1/reviews/intelligence?campaign_id={first.id}",
        headers=headers,
    )
    portfolio_response = client.get("/api/v1/reviews/portfolio", headers=headers)

    assert location_response.status_code == 200
    assert portfolio_response.status_code == 200
    assert location_response.json()["data"]["location_name"] == "Reno"
    assert portfolio_response.json()["data"]["summary"]["locations"] == 2
    serialized = str(portfolio_response.json()).lower()
    assert "dataforseo" not in serialized
    assert "provider_name" not in serialized

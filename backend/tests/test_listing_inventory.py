from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.models.authority import DirectoryListingObservation
from app.models.business_location import BusinessLocation
from app.models.campaign import Campaign
from app.models.organization_membership import OrganizationMembership
from app.models.user import User
from app.services import authority_service, listing_inventory_service
from app.services.cost_economics_service import CostEconomicsError


def _location_campaign(db_session, *, email: str = "a@example.com") -> tuple[User, Campaign, BusinessLocation]:
    user = db_session.query(User).filter(User.email == email).one()
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
        address_line1="100 Main Street",
        city="Reno",
        region="NV",
        postal_code="89501",
        country_code="US",
        latitude=39.5296,
        longitude=-119.8138,
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


def _listing_record(**overrides):
    record = {
        "source_key": "google_maps",
        "source_name": "Google Maps",
        "provider_name": "dataforseo",
        "external_id": "places/reno-junk-magicians",
        "status": "live",
        "business_name": "Junk Magicians",
        "address_line1": "100 Main St.",
        "city": "Reno",
        "region": "Nevada",
        "postal_code": "89501",
        "country_code": "US",
        "website_url": "https://www.junkmagiciansnv.com/",
        "primary_category": "Junk removal service",
        "directory_importance": "essential",
    }
    record.update(overrides)
    return record


def test_listing_inventory_records_exact_differences_and_history(db_session):
    user, campaign, _location = _location_campaign(db_session)
    first_time = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)

    first = listing_inventory_service.upsert_discovered_listings(
        db_session,
        tenant_id=user.tenant_id,
        campaign_id=campaign.id,
        records=[_listing_record()],
        observed_at=first_time,
    )[0]

    assert first.status == "inconsistent"
    assert first.field_differences == [
        {"field": "region", "expected": "NV", "found": "Nevada"}
    ]
    assert first.business_location_id == campaign.business_location_id
    assert first.provider_name == "dataforseo"

    second = listing_inventory_service.upsert_discovered_listings(
        db_session,
        tenant_id=user.tenant_id,
        campaign_id=campaign.id,
        records=[_listing_record(region="NV")],
        observed_at=first_time + timedelta(days=7),
    )[0]

    assert second.id == first.id
    assert second.status == "correct"
    assert second.field_differences == []
    assert second.last_verified_at.replace(tzinfo=UTC) == first_time + timedelta(days=7)
    observations = (
        db_session.query(DirectoryListingObservation)
        .filter(DirectoryListingObservation.listing_id == first.id)
        .order_by(DirectoryListingObservation.observed_at)
        .all()
    )
    assert [item.status for item in observations] == ["inconsistent", "correct"]


def test_listing_inventory_replay_is_idempotent_and_tenant_scoped(db_session):
    user, campaign, _location = _location_campaign(db_session)
    observed_at = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)
    for _ in range(2):
        listing_inventory_service.upsert_discovered_listings(
            db_session,
            tenant_id=user.tenant_id,
            campaign_id=campaign.id,
            records=[_listing_record(region="NV")],
            observed_at=observed_at,
        )

    rows = listing_inventory_service.list_inventory(
        db_session,
        tenant_id=user.tenant_id,
        campaign_id=campaign.id,
    )
    assert len(rows) == 1
    assert (
        db_session.query(DirectoryListingObservation)
        .filter(DirectoryListingObservation.listing_id == rows[0].id)
        .count()
        == 1
    )
    other_user = db_session.query(User).filter(User.email == "b@example.com").one()
    try:
        listing_inventory_service.list_inventory(
            db_session,
            tenant_id=other_user.tenant_id,
            campaign_id=campaign.id,
        )
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 404
    else:
        raise AssertionError("Cross-tenant listing inventory read should fail.")


def test_claimed_listing_still_reports_conflicting_business_details():
    assert (
        listing_inventory_service.classify_listing(
            requested_status="verified",
            differences=[{"field": "phone", "expected": "5550100", "found": "5550199"}],
            comparable_fields=4,
        )
        == "inconsistent"
    )


def test_listing_inventory_api_uses_customer_safe_truth(client, db_session, monkeypatch):
    user, campaign, _location = _location_campaign(db_session)
    listing_inventory_service.upsert_discovered_listings(
        db_session,
        tenant_id=user.tenant_id,
        campaign_id=campaign.id,
        records=[_listing_record(region="NV")],
    )
    login = client.post("/api/v1/auth/login", json={"email": "a@example.com", "password": "pass-a"})
    token = login.json()["data"]["access_token"]

    response = client.get(
        f"/api/v1/citations/inventory?campaign_id={campaign.id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["summary"]["confirmed"] == 1
    assert data["items"][0]["source_name"] == "Google Maps"
    assert "provider_name" not in data["items"][0]
    assert data["truth"]["correction_available"] is False
    assert data["truth"]["correction_access"] == {
        "plan_eligible": False,
        "correction_enabled": False,
        "required_plan": "Growth",
        "state": "plan_upgrade_required",
        "summary": (
            "Managed directory corrections require Growth. Public listing checks and "
            "manual correction guidance remain available."
        ),
    }
    assert "dataforseo" not in str(data).lower()

    def unavailable_plan_check(*_args, **_kwargs):
        raise CostEconomicsError(
            "Plan truth is temporarily unavailable.",
            reason_code="plan_truth_unavailable",
            status_code=409,
        )

    monkeypatch.setattr(
        authority_service,
        "require_commercial_feature",
        unavailable_plan_check,
    )
    unavailable_plan = client.get(
        f"/api/v1/citations/inventory?campaign_id={campaign.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert unavailable_plan.status_code == 200
    unavailable_access = unavailable_plan.json()["data"]["truth"]["correction_access"]
    assert unavailable_access["state"] == "plan_check_unavailable"
    assert unavailable_access["correction_enabled"] is False
    assert unavailable_plan.json()["data"]["items"]

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from app.models.authority import DirectoryListingDiscoveryRun
from app.models.business_location import BusinessLocation
from app.models.campaign import Campaign
from app.models.commercial_feature_activation import CommercialFeatureActivation
from app.models.cost_economics import CostLedgerEntry
from app.models.organization_membership import OrganizationMembership
from app.models.user import User
from app.services import listing_discovery_service, listing_inventory_service
from app.services.commercial_plan_service import apply_commercial_plan
from app.services.cost_economics_service import get_customer_credit_summary


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


def _provider_result() -> dict:
    return {
        "cost": Decimal("0.01236"),
        "items": [
            {
                "source_key": "google_maps",
                "source_name": "Google Maps",
                "provider_name": "dataforseo",
                "external_id": "ChIJ-test",
                "listing_url": "https://maps.example.test/junk-magicians",
                "status": "verified",
                "business_name": "Junk Magicians",
                "address_line1": "100 Main St",
                "city": "Reno",
                "region": "NV",
                "postal_code": "89501",
                "country_code": "US",
                "website_url": "https://www.junkmagiciansnv.com/",
                "primary_category": "Junk removal service",
                "directory_importance": "essential",
                "confidence": 1.0,
            },
            {
                "source_key": "google_maps",
                "source_name": "Google Maps",
                "provider_name": "dataforseo",
                "external_id": "other-business",
                "status": "live",
                "business_name": "Biggest Little City Tours",
                "website_url": "https://unrelated.example",
            },
        ],
    }


def test_listing_discovery_preview_is_allowance_controlled(db_session, monkeypatch):
    user, campaign, location = _location_campaign(db_session)
    monkeypatch.setattr(listing_discovery_service, "_credential_owner", lambda *_args: "platform")

    preview = listing_discovery_service.preview_run(
        db_session,
        tenant_id=user.tenant_id,
        organization_id=str(campaign.organization_id),
        campaign_id=campaign.id,
    )

    assert preview["business_location_id"] == location.id
    assert preview["estimated_credits"] == 2
    assert preview["can_start"] is True
    assert preview["correction_available"] is False
    assert "dataforseo" not in str(preview).lower()


def test_listing_discovery_marks_multiple_matches_from_one_source_as_duplicates():
    location = BusinessLocation(
        organization_id="org-1",
        name="Junk Magicians",
        domain="junkmagiciansnv.com",
    )
    records = [
        {
            "source_key": "google_maps",
            "external_id": "one",
            "business_name": "Junk Magicians",
        },
        {
            "source_key": "google_maps",
            "external_id": "two",
            "business_name": "Junk Magicians",
        },
    ]

    relevant = listing_discovery_service._relevant_records(location, records)

    assert [row["status"] for row in relevant] == ["duplicate", "duplicate"]


def test_listing_discovery_run_is_idempotent_filters_results_and_reconciles(
    db_session,
    monkeypatch,
):
    user, campaign, _location = _location_campaign(db_session)
    monkeypatch.setattr(listing_discovery_service, "_credential_owner", lambda *_args: "platform")
    monkeypatch.setattr(
        listing_discovery_service,
        "resolve_provider_credentials",
        lambda *_args: {"login": "api@example.com", "password": "secret"},
    )
    monkeypatch.setattr(
        listing_discovery_service.DataForSeoBusinessListingsProvider,
        "search",
        lambda _self, **_kwargs: _provider_result(),
    )

    run, created = listing_discovery_service.create_run(
        db_session,
        tenant_id=user.tenant_id,
        organization_id=str(campaign.organization_id),
        campaign_id=campaign.id,
        requested_by_user_id=user.id,
        idempotency_key="listing-check-one",
    )
    replay, replay_created = listing_discovery_service.create_run(
        db_session,
        tenant_id=user.tenant_id,
        organization_id=str(campaign.organization_id),
        campaign_id=campaign.id,
        requested_by_user_id=user.id,
        idempotency_key="listing-check-one",
    )
    result = listing_discovery_service.dispatch_run(
        db_session,
        tenant_id=user.tenant_id,
        run_id=run.id,
    )

    assert created is True
    assert replay_created is False
    assert replay.id == run.id
    assert result["status"] == "completed"
    assert result["result_count"] == 1
    assert "provider" not in result
    rows = listing_inventory_service.list_inventory(
        db_session,
        tenant_id=user.tenant_id,
        campaign_id=campaign.id,
    )
    assert [row.business_name for row in rows] == ["Junk Magicians"]
    refreshed = db_session.get(DirectoryListingDiscoveryRun, run.id)
    assert refreshed.provider_reported_cost == Decimal("0.01236000")
    reconciliation = (
        db_session.query(CostLedgerEntry)
        .filter(
            CostLedgerEntry.reservation_id == run.reservation_id,
            CostLedgerEntry.event_type == "reconciliation",
        )
        .one()
    )
    assert reconciliation.provider_reported_cost == Decimal("0.01236000")


def test_listing_provider_timeout_retains_conservative_cost_exposure(
    db_session,
    monkeypatch,
):
    user, campaign, _location = _location_campaign(db_session)
    monkeypatch.setattr(listing_discovery_service, "_credential_owner", lambda *_args: "platform")
    monkeypatch.setattr(
        listing_discovery_service,
        "resolve_provider_credentials",
        lambda *_args: {"login": "api@example.com", "password": "secret"},
    )
    calls: list[str] = []

    def _timeout_after_paid_call(_self, **_kwargs):
        calls.append("started")
        raise TimeoutError("provider response was not received")

    monkeypatch.setattr(
        listing_discovery_service.DataForSeoBusinessListingsProvider,
        "search",
        _timeout_after_paid_call,
    )
    run, _created = listing_discovery_service.create_run(
        db_session,
        tenant_id=user.tenant_id,
        organization_id=str(campaign.organization_id),
        campaign_id=campaign.id,
        requested_by_user_id=user.id,
        idempotency_key="listing-provider-timeout",
    )
    reservation = db_session.get(CostLedgerEntry, run.reservation_id)
    estimated_cost = Decimal(reservation.estimated_cost)

    result = listing_discovery_service.dispatch_run(
        db_session,
        tenant_id=user.tenant_id,
        run_id=run.id,
    )

    assert calls == ["started"]
    assert result["status"] == "failed"
    reconciliation = (
        db_session.query(CostLedgerEntry)
        .filter(
            CostLedgerEntry.reservation_id == run.reservation_id,
            CostLedgerEntry.event_type == "reconciliation",
        )
        .one()
    )
    assert Decimal(reconciliation.provider_reported_cost) == estimated_cost
    assert (
        db_session.query(CostLedgerEntry)
        .filter(
            CostLedgerEntry.reservation_id == run.reservation_id,
            CostLedgerEntry.event_type == "release",
        )
        .count()
        == 0
    )
    credits = get_customer_credit_summary(
        db_session, organization_id=str(campaign.organization_id)
    )["credits"]
    assert credits["reserved"] == 0
    assert credits["used"] > 0


def test_queued_listing_check_is_released_without_provider_call_after_downgrade(
    db_session,
    monkeypatch,
):
    user, campaign, location = _location_campaign(db_session)
    apply_commercial_plan(
        db_session,
        organization_id=str(campaign.organization_id),
        plan_code="multi_location",
    )
    db_session.add(
        BusinessLocation(
            organization_id=campaign.organization_id,
            name="Second covered shop",
            status="active",
        )
    )
    db_session.commit()
    monkeypatch.setattr(listing_discovery_service, "_credential_owner", lambda *_args: "platform")
    run, _created = listing_discovery_service.create_run(
        db_session,
        tenant_id=user.tenant_id,
        organization_id=str(campaign.organization_id),
        campaign_id=campaign.id,
        requested_by_user_id=user.id,
        idempotency_key="listing-before-downgrade",
    )
    apply_commercial_plan(
        db_session,
        organization_id=str(campaign.organization_id),
        plan_code="solo",
    )
    db_session.commit()
    calls: list[dict] = []
    monkeypatch.setattr(
        listing_discovery_service.DataForSeoBusinessListingsProvider,
        "search",
        lambda _self, **kwargs: calls.append(kwargs),
    )

    result = listing_discovery_service.dispatch_run(
        db_session,
        tenant_id=user.tenant_id,
        run_id=run.id,
    )

    assert calls == []
    assert result["status"] == "failed"
    refreshed = db_session.get(DirectoryListingDiscoveryRun, run.id)
    assert refreshed.error_code == "active_location_overage_blocks_provider_work"
    assert (
        db_session.query(CostLedgerEntry)
        .filter(
            CostLedgerEntry.reservation_id == run.reservation_id,
            CostLedgerEntry.event_type == "release",
        )
        .count()
        == 1
    )
    assert db_session.get(BusinessLocation, location.id).status == "active"


def test_observe_queued_listing_is_stopped_and_released_after_activation(
    db_session,
    monkeypatch,
):
    user, campaign, _location = _location_campaign(db_session)
    activation = db_session.get(
        CommercialFeatureActivation,
        "active_location_allowance",
    )
    assert activation is not None
    activation.state = "observe"
    db_session.add(
        BusinessLocation(
            organization_id=campaign.organization_id,
            name="Observed listing overage shop",
            status="active",
        )
    )
    db_session.commit()
    monkeypatch.setattr(
        listing_discovery_service,
        "_credential_owner",
        lambda *_args: "platform",
    )
    run, _created = listing_discovery_service.create_run(
        db_session,
        tenant_id=user.tenant_id,
        organization_id=str(campaign.organization_id),
        campaign_id=campaign.id,
        requested_by_user_id=user.id,
        idempotency_key="listing-observe-before-activation",
    )

    activation = db_session.get(
        CommercialFeatureActivation,
        "active_location_allowance",
    )
    activation.state = "enforced"
    db_session.commit()
    calls: list[dict] = []
    monkeypatch.setattr(
        listing_discovery_service.DataForSeoBusinessListingsProvider,
        "search",
        lambda _self, **kwargs: calls.append(kwargs),
    )

    result = listing_discovery_service.dispatch_run(
        db_session,
        tenant_id=user.tenant_id,
        run_id=run.id,
    )

    assert calls == []
    assert result["status"] == "failed"
    assert (
        db_session.get(DirectoryListingDiscoveryRun, run.id).error_code
        == "active_location_overage_blocks_provider_work"
    )
    assert (
        db_session.query(CostLedgerEntry)
        .filter(
            CostLedgerEntry.reservation_id == run.reservation_id,
            CostLedgerEntry.event_type == "release",
        )
        .count()
        == 1
    )
    assert get_customer_credit_summary(
        db_session, organization_id=str(campaign.organization_id)
    )["credits"]["reserved"] == 0


def test_queued_listing_check_rejects_archived_target_before_provider_call(
    db_session,
    monkeypatch,
):
    user, campaign, location = _location_campaign(db_session)
    monkeypatch.setattr(listing_discovery_service, "_credential_owner", lambda *_args: "platform")
    run, _created = listing_discovery_service.create_run(
        db_session,
        tenant_id=user.tenant_id,
        organization_id=str(campaign.organization_id),
        campaign_id=campaign.id,
        requested_by_user_id=user.id,
        idempotency_key="listing-before-archive",
    )
    location.status = "archived"
    db_session.commit()
    calls: list[dict] = []
    monkeypatch.setattr(
        listing_discovery_service.DataForSeoBusinessListingsProvider,
        "search",
        lambda _self, **kwargs: calls.append(kwargs),
    )

    result = listing_discovery_service.dispatch_run(
        db_session,
        tenant_id=user.tenant_id,
        run_id=run.id,
    )

    assert calls == []
    assert result["status"] == "failed"
    assert (
        db_session.get(DirectoryListingDiscoveryRun, run.id).error_code
        == "active_business_location_required_for_provider_work"
    )
    assert (
        db_session.query(CostLedgerEntry)
        .filter(
            CostLedgerEntry.reservation_id == run.reservation_id,
            CostLedgerEntry.event_type == "release",
        )
        .count()
        == 1
    )
    assert get_customer_credit_summary(
        db_session, organization_id=str(campaign.organization_id)
    )["credits"]["reserved"] == 0


def test_listing_discovery_api_hides_internal_provider(client, db_session, monkeypatch):
    user, campaign, _location = _location_campaign(db_session)
    monkeypatch.setattr(listing_discovery_service, "_credential_owner", lambda *_args: "platform")
    monkeypatch.setattr(
        listing_discovery_service,
        "resolve_provider_credentials",
        lambda *_args: {"login": "api@example.com", "password": "secret"},
    )
    monkeypatch.setattr(
        listing_discovery_service.DataForSeoBusinessListingsProvider,
        "search",
        lambda _self, **_kwargs: _provider_result(),
    )
    login = client.post("/api/v1/auth/login", json={"email": "a@example.com", "password": "pass-a"})
    token = login.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    preview = client.post(
        "/api/v1/citations/discovery/preview",
        headers=headers,
        json={"campaign_id": campaign.id},
    )
    run = client.post(
        "/api/v1/citations/discovery/runs",
        headers=headers,
        json={"campaign_id": campaign.id, "idempotency_key": "api-listing-check-one"},
    )
    latest = client.get(
        f"/api/v1/citations/discovery/latest?campaign_id={campaign.id}",
        headers=headers,
    )

    assert preview.status_code == 200
    assert run.status_code == 202
    assert run.json()["data"]["run"]["status"] == "completed"
    assert latest.status_code == 200
    assert latest.json()["data"]["run"]["id"] == run.json()["data"]["run"]["id"]
    assert "dataforseo" not in str(preview.json()).lower()
    assert "dataforseo" not in str(run.json()).lower()
    assert "dataforseo" not in str(latest.json()).lower()

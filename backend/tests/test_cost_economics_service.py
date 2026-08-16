from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.models.business_location import BusinessLocation
from app.models.campaign import Campaign
from app.models.commercial_feature_activation import CommercialFeatureActivation
from app.models.cost_economics import CostLedgerEntry, OrganizationCostAllocation, ProviderPriceCard
from app.models.organization import Organization
from app.services.commercial_plan_service import apply_commercial_plan
from app.services.cost_economics_service import (
    CostAllowanceExceeded,
    CostEconomicsError,
    authorize_reserved_provider_dispatch,
    get_allowance_summary,
    get_customer_credit_summary,
    get_margin_report,
    list_tier_margin_models,
    reconcile_provider_cost,
    record_monthly_allocation,
    release_provider_cost,
    reserve_provider_cost,
)
from app.services.rank_service import _dataforseo_keyword_cost_multiplier


def _reserve(db_session, organization_id: str, *, key: str, owner: str = "platform", quantity: int = 10):
    return reserve_provider_cost(
        db_session,
        organization_id=organization_id,
        provider_name="dataforseo",
        capability="rank_tracking",
        operation="google_organic_live_advanced",
        credential_owner=owner,
        quantity=quantity,
        idempotency_key=key,
        now=datetime(2026, 7, 30, 15, 0, tzinfo=UTC),
    )


def test_platform_cost_reserves_reconciles_and_is_idempotent(db_session, create_test_org) -> None:
    org = create_test_org(name="Cost ledger platform org")
    db_session.commit()

    reservation = _reserve(db_session, org.id, key="rank:test:one")
    replay = _reserve(db_session, org.id, key="rank:test:one")

    assert replay.id == reservation.id
    assert Decimal(reservation.estimated_cost) == Decimal("0.02000000")
    assert Decimal(reservation.budget_impact_cost) == Decimal("0.02000000")
    assert reservation.price_card_version == "dataforseo-google-organic-2026-07-30-v1"
    assert reservation.customer_credit_units == 2
    assert reservation.credit_policy_version == "insight-credits-2026-08-v1"

    reconciliation = reconcile_provider_cost(
        db_session,
        reservation=reservation,
        provider_reported_cost=Decimal("0.018"),
        now=datetime(2026, 7, 30, 15, 1, tzinfo=UTC),
    )
    assert Decimal(reconciliation.provider_reported_cost) == Decimal("0.01800000")
    assert Decimal(reconciliation.budget_impact_cost) == Decimal("-0.00200000")
    assert reconciliation.customer_credit_units == 0

    summary = get_allowance_summary(
        db_session,
        organization_id=org.id,
        now=datetime(2026, 7, 30, 16, 0, tzinfo=UTC),
    )
    assert summary["plan"]["name"] == "Solo"
    assert summary["allowance"]["monthly"] == 19.95
    assert summary["allowance"]["used"] == 0.02
    assert summary["allowance"]["reserved"] == 0.0

    credits = get_customer_credit_summary(
        db_session,
        organization_id=org.id,
        now=datetime(2026, 7, 30, 16, 0, tzinfo=UTC),
    )
    assert credits["credits"] == {
        "name": "Insight Credits",
        "monthly": 1995,
        "used": 2,
        "reserved": 0,
        "remaining": 1993,
        "percent_committed": 0.1,
        "warning_level": None,
        "blocked": False,
    }
    assert credits["recent_activity"][0]["state"] == "completed"
    assert credits["recent_activity"][0]["credits"] == 2


def test_existing_reservation_retry_is_denied_after_over_limit_downgrade(
    db_session, create_test_org
) -> None:
    org = create_test_org(name="Reservation downgrade guard org")
    apply_commercial_plan(db_session, organization_id=org.id, plan_code="multi_location")
    locations = [
        BusinessLocation(organization_id=org.id, name=f"Covered location {index}", status="active")
        for index in range(2)
    ]
    db_session.add_all(locations)
    db_session.commit()
    reservation = reserve_provider_cost(
        db_session,
        organization_id=org.id,
        provider_name="dataforseo",
        capability="rank_tracking",
        operation="google_organic_live_advanced",
        credential_owner="platform",
        quantity=1,
        idempotency_key="rank:reserved-before-downgrade",
        business_location_id=locations[0].id,
    )

    apply_commercial_plan(db_session, organization_id=org.id, plan_code="solo")
    db_session.commit()

    with pytest.raises(CostEconomicsError) as exc_info:
        reserve_provider_cost(
            db_session,
            organization_id=org.id,
            provider_name="dataforseo",
            capability="rank_tracking",
            operation="google_organic_live_advanced",
            credential_owner="platform",
            quantity=1,
            idempotency_key="rank:reserved-before-downgrade",
            business_location_id=locations[0].id,
        )

    assert exc_info.value.reason_code == "active_location_overage_blocks_provider_work"
    assert (
        db_session.query(CostLedgerEntry)
        .filter(
            CostLedgerEntry.organization_id == org.id,
            CostLedgerEntry.idempotency_key == "rank:reserved-before-downgrade",
            CostLedgerEntry.event_type == "reservation",
        )
        .count()
        == 1
    )
    assert db_session.get(CostLedgerEntry, reservation.id) is not None


def test_observe_bridge_allows_overage_reservation_but_keeps_location_mapping_guard(
    db_session, create_test_org
) -> None:
    org = create_test_org(name="Observed provider allowance org")
    activation = db_session.get(
        CommercialFeatureActivation,
        "active_location_allowance",
    )
    assert activation is not None
    activation.state = "observe"
    locations = [
        BusinessLocation(
            organization_id=org.id,
            name=f"Observed provider shop {index}",
            status="active",
        )
        for index in range(2)
    ]
    db_session.add_all(locations)
    db_session.commit()

    reservation = reserve_provider_cost(
        db_session,
        organization_id=org.id,
        provider_name="dataforseo",
        capability="rank_tracking",
        operation="google_organic_live_advanced",
        credential_owner="platform",
        quantity=1,
        idempotency_key="rank:observe-overage",
        business_location_id=locations[0].id,
    )
    assert reservation.event_type == "reservation"

    activation = db_session.get(
        CommercialFeatureActivation,
        "active_location_allowance",
    )
    activation.state = "enforced"
    db_session.commit()
    with pytest.raises(CostEconomicsError) as activation_exc:
        authorize_reserved_provider_dispatch(db_session, reservation=reservation)
    assert activation_exc.value.reason_code == (
        "active_location_overage_blocks_provider_work"
    )
    assert (
        db_session.query(CostLedgerEntry)
        .filter(
            CostLedgerEntry.reservation_id == reservation.id,
            CostLedgerEntry.event_type == "release",
        )
        .count()
        == 1
    )

    activation = db_session.get(
        CommercialFeatureActivation,
        "active_location_allowance",
    )
    activation.state = "observe"
    unmapped = Campaign(
        tenant_id=org.id,
        organization_id=org.id,
        business_location_id=None,
        name="Observed unmapped campaign",
        domain="observed-unmapped.example",
    )
    db_session.add(unmapped)
    db_session.commit()
    with pytest.raises(CostEconomicsError) as exc_info:
        reserve_provider_cost(
            db_session,
            organization_id=org.id,
            provider_name="dataforseo",
            capability="rank_tracking",
            operation="google_organic_live_advanced",
            credential_owner="platform",
            quantity=1,
            idempotency_key="rank:observe-unmapped",
            campaign_id=unmapped.id,
            business_location_id=None,
        )
    assert exc_info.value.reason_code == (
        "active_business_location_required_for_provider_work"
    )


def test_dispatch_recheck_releases_when_location_archived_after_reservation(
    db_session, create_test_org
) -> None:
    org = create_test_org(name="Archived between reserve and dispatch org")
    location = BusinessLocation(
        organization_id=org.id,
        name="Archive at dispatch shop",
        status="active",
    )
    db_session.add(location)
    db_session.commit()
    reservation = reserve_provider_cost(
        db_session,
        organization_id=org.id,
        provider_name="dataforseo",
        capability="rank_tracking",
        operation="google_organic_live_advanced",
        credential_owner="platform",
        quantity=1,
        idempotency_key="rank:archive-after-reserve",
        business_location_id=location.id,
    )
    location.status = "archived"
    db_session.commit()

    with pytest.raises(CostEconomicsError) as exc_info:
        authorize_reserved_provider_dispatch(db_session, reservation=reservation)

    assert exc_info.value.reason_code == (
        "active_business_location_required_for_provider_work"
    )
    assert (
        db_session.query(CostLedgerEntry)
        .filter(
            CostLedgerEntry.reservation_id == reservation.id,
            CostLedgerEntry.event_type == "release",
        )
        .count()
        == 1
    )


def test_dispatch_recheck_rejects_already_terminal_reservation_without_second_event(
    db_session, create_test_org
) -> None:
    org = create_test_org(name="Finalized provider dispatch org")
    reservation = _reserve(db_session, org.id, key="rank:already-finalized", quantity=1)
    release_provider_cost(db_session, reservation=reservation)

    with pytest.raises(CostEconomicsError) as exc_info:
        authorize_reserved_provider_dispatch(db_session, reservation=reservation)

    assert exc_info.value.reason_code == "provider_dispatch_already_finalized"
    assert (
        db_session.query(CostLedgerEntry)
        .filter(
            CostLedgerEntry.reservation_id == reservation.id,
            CostLedgerEntry.event_type == "release",
        )
        .count()
        == 1
    )


def test_dispatch_recheck_releases_when_organization_becomes_inactive(
    db_session, create_test_org
) -> None:
    org = create_test_org(name="Inactive between reserve and dispatch org")
    reservation = _reserve(db_session, org.id, key="rank:inactive-after-reserve", quantity=1)
    locked_org = db_session.get(Organization, org.id)
    locked_org.status = "suspended"
    db_session.commit()

    with pytest.raises(CostEconomicsError) as exc_info:
        authorize_reserved_provider_dispatch(db_session, reservation=reservation)

    assert exc_info.value.reason_code == "organization_inactive_for_commercial_work"
    assert (
        db_session.query(CostLedgerEntry)
        .filter(
            CostLedgerEntry.reservation_id == reservation.id,
            CostLedgerEntry.event_type == "release",
        )
        .count()
        == 1
    )


def test_provider_reservation_rejects_archived_target_location(
    db_session, create_test_org
) -> None:
    org = create_test_org(name="Archived location provider guard org")
    location = BusinessLocation(
        organization_id=org.id,
        name="Archived shop",
        status="archived",
    )
    db_session.add(location)
    db_session.commit()

    with pytest.raises(CostEconomicsError) as exc_info:
        reserve_provider_cost(
            db_session,
            organization_id=org.id,
            provider_name="dataforseo",
            capability="rank_tracking",
            operation="google_organic_live_advanced",
            credential_owner="platform",
            quantity=1,
            idempotency_key="rank:archived-location",
            business_location_id=location.id,
        )

    assert exc_info.value.reason_code == "active_business_location_required_for_provider_work"
    assert (
        db_session.query(CostLedgerEntry)
        .filter(CostLedgerEntry.idempotency_key == "rank:archived-location")
        .count()
        == 0
    )


def test_campaign_scoped_reservation_requires_exact_active_location_mapping(
    db_session, create_test_org
) -> None:
    org = create_test_org(name="Campaign location mapping guard org")
    apply_commercial_plan(db_session, organization_id=org.id, plan_code="multi_location")
    locations = [
        BusinessLocation(organization_id=org.id, name=f"Mapped shop {index}", status="active")
        for index in range(2)
    ]
    db_session.add_all(locations)
    db_session.flush()
    unmapped = Campaign(
        tenant_id=org.id,
        organization_id=org.id,
        business_location_id=None,
        name="Legacy unmapped campaign",
        domain="legacy-unmapped.example",
    )
    mapped = Campaign(
        tenant_id=org.id,
        organization_id=org.id,
        business_location_id=locations[0].id,
        name="Mapped campaign",
        domain="mapped.example",
    )
    db_session.add_all([unmapped, mapped])
    db_session.commit()

    attempts = [
        ("rank:unmapped-campaign", unmapped.id, None),
        ("rank:mismatched-campaign", mapped.id, locations[1].id),
    ]
    for key, campaign_id, business_location_id in attempts:
        with pytest.raises(CostEconomicsError) as exc_info:
            reserve_provider_cost(
                db_session,
                organization_id=org.id,
                provider_name="dataforseo",
                capability="rank_tracking",
                operation="google_organic_live_advanced",
                credential_owner="platform",
                quantity=1,
                idempotency_key=key,
                campaign_id=campaign_id,
                business_location_id=business_location_id,
            )
        assert exc_info.value.reason_code == (
            "active_business_location_required_for_provider_work"
        )

    assert (
        db_session.query(CostLedgerEntry)
        .filter(CostLedgerEntry.idempotency_key.in_([item[0] for item in attempts]))
        .count()
        == 0
    )


def test_organization_credentials_do_not_consume_platform_cogs(db_session, create_test_org) -> None:
    org = create_test_org(name="BYO cost ledger org")
    db_session.commit()

    reservation = _reserve(
        db_session,
        org.id,
        key="rank:test:byo",
        owner="organization",
    )
    reconcile_provider_cost(
        db_session,
        reservation=reservation,
        provider_reported_cost=Decimal("0.02"),
        now=datetime(2026, 7, 30, 15, 1, tzinfo=UTC),
    )

    summary = get_allowance_summary(
        db_session,
        organization_id=org.id,
        now=datetime(2026, 7, 30, 16, 0, tzinfo=UTC),
    )
    assert summary["allowance"]["used"] == 0.0
    assert summary["allowance"]["reserved"] == 0.0
    assert summary["organization_owned_operations"] == 1
    assert Decimal(reservation.estimated_cost) == Decimal("0.02000000")
    assert Decimal(reservation.budget_impact_cost) == Decimal("0E-8")
    assert reservation.customer_credit_units == 0

    credits = get_customer_credit_summary(
        db_session,
        organization_id=org.id,
        now=datetime(2026, 7, 30, 16, 0, tzinfo=UTC),
    )
    assert credits["credits"]["used"] == 0
    assert credits["connected_account_actions"] == 1
    assert credits["recent_activity"][0]["state"] == "connected_account"


def test_platform_allowance_stops_before_dispatch(db_session, create_test_org) -> None:
    org = create_test_org(name="Hard allowance org")
    db_session.commit()

    _reserve(db_session, org.id, key="rank:test:first", quantity=1)
    _reserve(db_session, org.id, key="rank:test:full", quantity=9970)
    with pytest.raises(CostAllowanceExceeded) as exc_info:
        _reserve(db_session, org.id, key="rank:test:blocked", quantity=1)

    assert exc_info.value.budget == Decimal("19.95000000")
    assert exc_info.value.reason_code == "insight_credit_allowance_exhausted"
    assert (
        db_session.query(CostLedgerEntry)
        .filter(CostLedgerEntry.idempotency_key == "rank:test:blocked")
        .count()
        == 0
    )


def test_failed_provider_cost_is_released(db_session, create_test_org) -> None:
    org = create_test_org(name="Released cost org")
    db_session.commit()

    reservation = _reserve(db_session, org.id, key="rank:test:failed")
    released = release_provider_cost(db_session, reservation=reservation)
    replay = release_provider_cost(db_session, reservation=reservation)

    assert replay.id == released.id
    assert Decimal(released.budget_impact_cost) == Decimal("-0.02000000")
    assert released.customer_credit_units == -2
    summary = get_allowance_summary(db_session, organization_id=org.id)
    assert summary["allowance"]["used"] == 0.0
    assert summary["allowance"]["reserved"] == 0.0
    credits = get_customer_credit_summary(db_session, organization_id=org.id)
    assert credits["credits"]["used"] == 0
    assert credits["credits"]["reserved"] == 0
    assert credits["recent_activity"][0]["state"] == "returned"


@pytest.mark.parametrize(
    ("quantity", "expected_warning"),
    [(5000, 50), (7500, 75), (9000, 90)],
)
def test_allowance_warning_thresholds(
    db_session,
    create_test_org,
    quantity: int,
    expected_warning: int,
) -> None:
    org = create_test_org(name=f"Warning threshold {expected_warning}")
    db_session.commit()
    _reserve(
        db_session,
        org.id,
        key=f"rank:test:warning:{expected_warning}",
        quantity=quantity,
    )

    summary = get_allowance_summary(
        db_session,
        organization_id=org.id,
        now=datetime(2026, 7, 30, 16, 0, tzinfo=UTC),
    )

    assert summary["allowance"]["warning_level"] == expected_warning
    assert summary["recovery_actions"]


def test_ai_token_price_card_is_versioned_and_metered(db_session, create_test_org) -> None:
    org = create_test_org(name="Future AI usage org")
    db_session.add(
        ProviderPriceCard(
            provider_name="future_ai",
            capability="recommendation",
            operation="generate",
            model_name="model-a",
            version="model-a-2026-07-v1",
            unit="request",
            unit_cost=Decimal("0"),
            input_token_cost_per_million=Decimal("1.00"),
            cached_input_token_cost_per_million=Decimal("0.10"),
            output_token_cost_per_million=Decimal("4.00"),
            currency="USD",
            effective_from=datetime(2026, 7, 1, tzinfo=UTC),
            active=True,
        )
    )
    db_session.commit()

    reservation = reserve_provider_cost(
        db_session,
        organization_id=org.id,
        provider_name="future_ai",
        capability="recommendation",
        operation="generate",
        credential_owner="platform",
        quantity=1,
        idempotency_key="ai:test:one",
        model_name="model-a",
        input_tokens=1_000_000,
        cached_input_tokens=1_000_000,
        output_tokens=1_000_000,
        now=datetime(2026, 7, 30, tzinfo=UTC),
    )

    assert Decimal(reservation.estimated_cost) == Decimal("5.10000000")
    assert reservation.input_tokens == 1_000_000
    assert reservation.price_card_version == "model-a-2026-07-v1"


def test_margin_report_uses_latest_versioned_allocation(db_session, create_test_org) -> None:
    org = create_test_org(name="Margin report org")
    org.plan_type = "multi_location"
    db_session.commit()
    period = datetime(2026, 7, 1, tzinfo=UTC)

    first = record_monthly_allocation(
        db_session,
        organization_id=org.id,
        period=period,
        created_by_user_id=None,
        hosting_cost=10,
        storage_cost=2,
        email_cost=1,
        support_cost=20,
        other_cost=3,
    )
    second = record_monthly_allocation(
        db_session,
        organization_id=org.id,
        period=period,
        created_by_user_id=None,
        hosting_cost=12,
        storage_cost=3,
        email_cost=1,
        support_cost=20,
        other_cost=4,
    )
    report = get_margin_report(db_session, organization_id=org.id, period=period)

    assert first.version == 1
    assert second.version == 2
    assert report["allocation_version"] == 2
    assert report["revenue"] == 699.0
    assert report["total_cogs"] == 40.0
    assert report["gross_profit"] == 659.0
    assert report["modeled_heavy_use"]["gross_margin_percent"] == 85.0
    assert report["modeled_heavy_use"]["publishable"] is True
    assert db_session.query(OrganizationCostAllocation).filter_by(organization_id=org.id).count() == 2


def test_all_public_tiers_pass_the_approved_heavy_use_floor() -> None:
    models = list_tier_margin_models()
    assert [item["code"] for item in models] == ["solo", "multi_location", "enterprise"]
    assert all(item["heavy_use_margin_percent"] == 85.0 for item in models)
    assert all(item["publishable"] is True for item in models)


def test_historical_margin_uses_the_plan_revenue_snapshot(db_session, create_test_org) -> None:
    org = create_test_org(name="Historical plan snapshot org")
    org.plan_type = "standard"
    db_session.commit()
    reservation = _reserve(db_session, org.id, key="rank:test:historical")
    reconcile_provider_cost(
        db_session,
        reservation=reservation,
        provider_reported_cost="0.02",
        now=datetime(2026, 7, 30, 15, 1, tzinfo=UTC),
    )

    org = db_session.get(type(org), org.id)
    org.plan_type = "enterprise"
    db_session.commit()
    report = get_margin_report(
        db_session,
        organization_id=org.id,
        period=datetime(2026, 7, 1, tzinfo=UTC),
    )

    assert report["organization"]["plan_code"] == "solo"
    assert report["revenue"] == 399.0
    assert report["platform_api_cost"] == 0.02


def test_dataforseo_advanced_operators_reserve_documented_multipliers() -> None:
    assert _dataforseo_keyword_cost_multiplier("junk removal reno") == 1
    assert _dataforseo_keyword_cost_multiplier("site:example.com junk removal") == 5
    assert _dataforseo_keyword_cost_multiplier("site:example.com intitle:junk") == 25
    assert _dataforseo_keyword_cost_multiplier("website: example") == 1
    assert _dataforseo_keyword_cost_multiplier("allintext:junk removal") == 5

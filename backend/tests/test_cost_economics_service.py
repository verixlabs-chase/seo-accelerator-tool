from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.models.cost_economics import CostLedgerEntry, OrganizationCostAllocation, ProviderPriceCard
from app.services.cost_economics_service import (
    CostAllowanceExceeded,
    get_allowance_summary,
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

    reconciliation = reconcile_provider_cost(
        db_session,
        reservation=reservation,
        provider_reported_cost=Decimal("0.018"),
        now=datetime(2026, 7, 30, 15, 1, tzinfo=UTC),
    )
    assert Decimal(reconciliation.provider_reported_cost) == Decimal("0.01800000")
    assert Decimal(reconciliation.budget_impact_cost) == Decimal("-0.00200000")

    summary = get_allowance_summary(
        db_session,
        organization_id=org.id,
        now=datetime(2026, 7, 30, 16, 0, tzinfo=UTC),
    )
    assert summary["plan"]["name"] == "Solo"
    assert summary["allowance"]["monthly"] == 14.95
    assert summary["allowance"]["used"] == 0.02
    assert summary["allowance"]["reserved"] == 0.0


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
    )

    summary = get_allowance_summary(db_session, organization_id=org.id)
    assert summary["allowance"]["used"] == 0.0
    assert summary["allowance"]["reserved"] == 0.0
    assert summary["organization_owned_operations"] == 1
    assert Decimal(reservation.estimated_cost) == Decimal("0.02000000")
    assert Decimal(reservation.budget_impact_cost) == Decimal("0E-8")


def test_platform_allowance_stops_before_dispatch(db_session, create_test_org) -> None:
    org = create_test_org(name="Hard allowance org")
    db_session.commit()

    _reserve(db_session, org.id, key="rank:test:full", quantity=7475)
    with pytest.raises(CostAllowanceExceeded) as exc_info:
        _reserve(db_session, org.id, key="rank:test:blocked", quantity=1)

    assert exc_info.value.budget == Decimal("14.95000000")
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
    summary = get_allowance_summary(db_session, organization_id=org.id)
    assert summary["allowance"]["used"] == 0.0
    assert summary["allowance"]["reserved"] == 0.0


@pytest.mark.parametrize(
    ("quantity", "expected_warning"),
    [(3738, 50), (5607, 75), (6728, 90)],
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
    reconcile_provider_cost(db_session, reservation=reservation, provider_reported_cost="0.02")

    org = db_session.get(type(org), org.id)
    org.plan_type = "enterprise"
    db_session.commit()
    report = get_margin_report(
        db_session,
        organization_id=org.id,
        period=datetime(2026, 7, 1, tzinfo=UTC),
    )

    assert report["organization"]["plan_code"] == "solo"
    assert report["revenue"] == 299.0
    assert report["platform_api_cost"] == 0.02


def test_dataforseo_advanced_operators_reserve_documented_multipliers() -> None:
    assert _dataforseo_keyword_cost_multiplier("junk removal reno") == 1
    assert _dataforseo_keyword_cost_multiplier("site:example.com junk removal") == 5
    assert _dataforseo_keyword_cost_multiplier("site:example.com intitle:junk") == 25
    assert _dataforseo_keyword_cost_multiplier("website: example") == 1
    assert _dataforseo_keyword_cost_multiplier("allintext:junk removal") == 5

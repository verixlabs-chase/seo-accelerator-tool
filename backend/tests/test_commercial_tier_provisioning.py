from __future__ import annotations

import pytest

import app.services.commercial_plan_service as commercial_plan_service
import app.services.location_allowance_service as location_allowance_service
from app.models.business_location import BusinessLocation
from app.domain.commercial_tiers import (
    COMMERCIAL_LEGACY_TIER_VERSION,
    legacy_tier_code_for_plan,
)
from app.domain.entitlement_codes import LIMIT_ACTIVE_LOCATIONS
from app.models.commercial_feature_activation import CommercialFeatureActivation
from app.models.entitlement import Entitlement
from app.models.tier_profile import TierProfile
from app.services.commercial_plan_service import apply_commercial_plan
from app.services.business_location_service import create_business_location_with_portfolio
from app.services.location_allowance_service import (
    ActiveLocationAllowanceError,
    get_active_location_allowance,
)
from app.services.provisioning_service import (
    TierProfileValidationError,
    ensure_default_tier_profile,
    ensure_organization_provisioned,
)
from tests.helpers.economic_setup import ensure_test_tier_profile


class _FirstQueryMiss:
    def __init__(self, query) -> None:
        self.query = query

    def filter(self, *criteria):
        self.query = self.query.filter(*criteria)
        return self

    def first(self):
        return None


class _OneQueryMiss:
    def __init__(self, query) -> None:
        self.query = query

    def filter(self, *criteria):
        self.query = self.query.filter(*criteria)
        return self

    def one_or_none(self):
        return None


def test_default_profile_recomputes_saved_template_hash_before_reuse(db_session) -> None:
    profile = (
        db_session.query(TierProfile)
        .filter(
            TierProfile.tier_code == "standard",
            TierProfile.version == COMMERCIAL_LEGACY_TIER_VERSION,
        )
        .one()
    )
    corrupted = dict(profile.entitlement_template_json)
    rows = [dict(item) for item in corrupted["entitlements"]]
    rows[0]["is_enforced"] = False
    profile.entitlement_template_json = {"entitlements": rows}
    db_session.commit()

    with pytest.raises(TierProfileValidationError, match="current catalog"):
        ensure_default_tier_profile(db_session)


def test_default_profile_revalidates_integrity_error_race_winner(
    db_session, monkeypatch
) -> None:
    profile = (
        db_session.query(TierProfile)
        .filter(
            TierProfile.tier_code == "standard",
            TierProfile.version == COMMERCIAL_LEGACY_TIER_VERSION,
        )
        .one()
    )
    profile.is_active = False
    db_session.commit()
    original_query = db_session.query
    tier_profile_query_count = 0

    def race_query(*entities, **kwargs):
        nonlocal tier_profile_query_count
        query = original_query(*entities, **kwargs)
        if entities == (TierProfile,):
            tier_profile_query_count += 1
            if tier_profile_query_count == 1:
                return _FirstQueryMiss(query)
        return query

    monkeypatch.setattr(db_session, "query", race_query)

    with pytest.raises(TierProfileValidationError, match="current catalog"):
        ensure_default_tier_profile(db_session)

    assert tier_profile_query_count == 2


def test_existing_organization_with_inactive_saved_profile_fails_closed(
    db_session, create_test_org
) -> None:
    organization = create_test_org(name="Broken provisioning profile org")
    profile = db_session.get(TierProfile, organization.tier_profile_id)
    profile.is_active = False
    db_session.commit()

    with pytest.raises(TierProfileValidationError, match="current catalog"):
        ensure_organization_provisioned(db_session, organization_id=organization.id)

    db_session.refresh(organization)
    assert organization.tier_profile_id == profile.id
    assert organization.plan_type == "solo"


@pytest.mark.parametrize(
    ("plan_code", "expected_limit"),
    [("solo", 1), ("multi_location", 10), ("enterprise", 20), ("internal_anchor", 20)],
)
def test_commercial_materializer_uses_published_location_limits(
    db_session, create_test_org, plan_code: str, expected_limit: int
) -> None:
    organization = create_test_org(name=f"Published {plan_code} allowance org")

    apply_commercial_plan(
        db_session,
        organization_id=organization.id,
        plan_code=plan_code,
    )
    db_session.commit()

    db_session.refresh(organization)
    allowance = get_active_location_allowance(db_session, organization=organization)
    assert organization.plan_type == plan_code
    assert organization.tier_version == COMMERCIAL_LEGACY_TIER_VERSION
    profile = db_session.get(TierProfile, organization.tier_profile_id)
    assert profile.tier_code == legacy_tier_code_for_plan(plan_code)
    assert profile.version == COMMERCIAL_LEGACY_TIER_VERSION
    assert allowance.included_locations == expected_limit


def test_solo_materializer_recovers_when_initial_standard_profile_lookup_misses(
    db_session, create_test_org, monkeypatch
) -> None:
    organization = create_test_org(name="Legacy Standard profile recovery org")
    original_query = db_session.query
    profile_query_count = 0

    def query_with_initial_profile_miss(*entities, **kwargs):
        nonlocal profile_query_count
        query = original_query(*entities, **kwargs)
        if entities == (TierProfile,):
            profile_query_count += 1
            if profile_query_count == 1:
                return _OneQueryMiss(query)
        return query

    monkeypatch.setattr(db_session, "query", query_with_initial_profile_miss)

    repaired, materialization = commercial_plan_service.apply_commercial_plan(
        db_session,
        organization_id=organization.id,
        plan_code="solo",
    )

    assert repaired.plan_type == "solo"
    assert materialization["tier_profile_id"] == repaired.tier_profile_id
    assert profile_query_count >= 2
    profile = db_session.get(TierProfile, repaired.tier_profile_id)
    assert profile is not None
    assert profile.tier_code == "standard"
    assert profile.version == COMMERCIAL_LEGACY_TIER_VERSION


def test_arbitrary_profile_cannot_override_solo_location_allowance(
    db_session, create_test_org
) -> None:
    organization = create_test_org(name="Unknown profile allowance guard org")
    custom = TierProfile(
        tier_code="custom_solo_override",
        display_name="Custom override",
        version=99,
        entitlement_template_json={"entitlements": []},
        deterministic_hash="f" * 64,
        is_active=True,
    )
    db_session.add(custom)
    db_session.flush()
    organization.tier_profile_id = custom.id
    organization.tier_version = 99
    entitlement = (
        db_session.query(Entitlement)
        .filter(
            Entitlement.organization_id == organization.id,
            Entitlement.code == "limit.active_locations",
        )
        .one()
    )
    entitlement.limit_value = 1_000
    db_session.commit()

    with pytest.raises(ActiveLocationAllowanceError) as exc_info:
        get_active_location_allowance(db_session, organization=organization)

    assert exc_info.value.reason_code == "active_location_allowance_unavailable"


def test_pre_migration_v1_org_lazily_bootstraps_allowance_in_observe_mode(
    db_session, create_test_org, monkeypatch
) -> None:
    organization = create_test_org(name="Pre-migration bridge org")
    original_profile_id = organization.tier_profile_id
    (
        db_session.query(Entitlement)
        .filter(
            Entitlement.organization_id == organization.id,
            Entitlement.code == LIMIT_ACTIVE_LOCATIONS,
        )
        .delete(synchronize_session=False)
    )
    db_session.flush()

    class _PreMigrationInspector:
        @staticmethod
        def has_table(_table_name: str) -> bool:
            return False

    monkeypatch.setattr(
        location_allowance_service,
        "inspect",
        lambda _bind: _PreMigrationInspector(),
    )

    allowance = get_active_location_allowance(db_session, organization=organization)

    assert allowance.included_locations == 1
    assert allowance.capacity_enforced is False
    assert organization.tier_profile_id == original_profile_id
    saved = (
        db_session.query(Entitlement)
        .filter(
            Entitlement.organization_id == organization.id,
            Entitlement.code == LIMIT_ACTIVE_LOCATIONS,
        )
        .one()
    )
    assert saved.limit_value == 1


def test_old_runtime_plan_only_changes_reconcile_stale_bridge_allowance(
    db_session, create_test_org
) -> None:
    organization = create_test_org(name="Mixed-version billing bridge org")
    enterprise_profile = ensure_test_tier_profile(db_session, plan_code="enterprise")
    organization.tier_profile_id = enterprise_profile.id
    organization.tier_version = enterprise_profile.version
    organization.plan_type = "multi_location"
    db_session.commit()

    upgraded = get_active_location_allowance(db_session, organization=organization)
    assert upgraded.included_locations == 10
    assert upgraded.tier_profile_id == enterprise_profile.id

    # Simulate a 0154 Stripe worker: it updates only plan_type, leaving the
    # valid 10-location bridge row and mismatched v1 pointer untouched.
    organization.plan_type = "solo"
    db_session.commit()
    downgraded = get_active_location_allowance(db_session, organization=organization)

    assert downgraded.included_locations == 1
    assert downgraded.tier_profile_id == enterprise_profile.id
    assert (
        db_session.query(Entitlement.limit_value)
        .filter(
            Entitlement.organization_id == organization.id,
            Entitlement.code == LIMIT_ACTIVE_LOCATIONS,
        )
        .scalar()
        == 1
    )


def test_corrupt_bridge_allowance_is_not_silently_repaired(
    db_session, create_test_org
) -> None:
    organization = create_test_org(name="Corrupt bridge allowance org")
    entitlement = (
        db_session.query(Entitlement)
        .filter(
            Entitlement.organization_id == organization.id,
            Entitlement.code == LIMIT_ACTIVE_LOCATIONS,
        )
        .one()
    )
    entitlement.limit_value = 7
    db_session.commit()

    with pytest.raises(ActiveLocationAllowanceError) as exc_info:
        get_active_location_allowance(db_session, organization=organization)

    assert exc_info.value.reason_code == "active_location_allowance_unavailable"
    db_session.refresh(entitlement)
    assert entitlement.limit_value == 7


@pytest.mark.parametrize("activation_problem", ["missing", "catalog_mismatch"])
def test_activation_configuration_failure_is_fail_closed(
    db_session, create_test_org, activation_problem: str
) -> None:
    organization = create_test_org(name=f"Activation {activation_problem} org")
    activation = db_session.get(
        CommercialFeatureActivation,
        "active_location_allowance",
    )
    assert activation is not None
    if activation_problem == "missing":
        db_session.delete(activation)
    else:
        activation.catalog_version = "unexpected-catalog"
    db_session.commit()

    with pytest.raises(ActiveLocationAllowanceError) as exc_info:
        get_active_location_allowance(db_session, organization=organization)

    assert exc_info.value.reason_code == "active_location_allowance_unavailable"


def test_inactive_organization_cannot_create_location_even_in_observe_mode(
    db_session, create_test_org
) -> None:
    organization = create_test_org(name="Inactive commercial work org")
    activation = db_session.get(
        CommercialFeatureActivation,
        "active_location_allowance",
    )
    activation.state = "observe"
    organization.status = "closure_pending"
    db_session.commit()

    with pytest.raises(ActiveLocationAllowanceError) as exc_info:
        create_business_location_with_portfolio(
            db_session,
            organization_id=organization.id,
            name="Must not be created",
            domain=None,
            primary_city=None,
        )

    assert exc_info.value.reason_code == "organization_inactive_for_commercial_work"
    assert (
        db_session.query(BusinessLocation)
        .filter(BusinessLocation.organization_id == organization.id)
        .count()
        == 0
    )

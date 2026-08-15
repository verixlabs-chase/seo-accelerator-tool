from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
import json
from typing import Any

from sqlalchemy import func, inspect
from sqlalchemy.orm import Session

from app.domain.commercial_tiers import (
    COMMERCIAL_TIER_CATALOG_VERSION,
    COMMERCIAL_TIERS,
    normalize_commercial_plan_code,
)
from app.domain.entitlement_codes import LIMIT_ACTIVE_LOCATIONS
from app.models.business_location import BusinessLocation
from app.models.campaign import Campaign
from app.models.commercial_feature_activation import CommercialFeatureActivation
from app.models.entitlement import Entitlement, EntitlementResetPeriod, EntitlementValueType
from app.models.organization import Organization
from app.models.tier_profile import TierProfile
from app.services.provisioning_service import (
    TierProfileValidationError,
    validate_commercial_profile_pointer,
)


_LOCK_SUPPORTED_DIALECTS = {"postgresql", "mysql", "mariadb", "oracle"}
ACTIVE_LOCATION_ACTIVATION_CODE = "active_location_allowance"
ACTIVE_LOCATION_STATE_OBSERVE = "observe"
ACTIVE_LOCATION_STATE_ENFORCED = "enforced"


@dataclass(frozen=True)
class ActiveLocationAllowance:
    organization_id: str
    plan_code: str
    plan_name: str
    tier_profile_id: str
    tier_version: int
    included_locations: int
    active_locations: int
    capacity_enforced: bool

    @property
    def remaining_locations(self) -> int:
        return max(0, self.included_locations - self.active_locations)

    @property
    def over_limit_by(self) -> int:
        return max(0, self.active_locations - self.included_locations)

    @property
    def can_activate_location(self) -> bool:
        return not self.capacity_enforced or self.active_locations < self.included_locations


class ActiveLocationAllowanceError(RuntimeError):
    def __init__(self, message: str, *, reason_code: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code

    def safe_details(self) -> dict[str, Any]:
        return {"message": str(self), "reason_code": self.reason_code}


class ActiveLocationAllowanceExceeded(ActiveLocationAllowanceError):
    def __init__(
        self,
        *,
        allowance: ActiveLocationAllowance,
        requested_delta: int,
    ) -> None:
        super().__init__(
            (
                f"Your {allowance.plan_name} plan includes "
                f"{allowance.included_locations} active location"
                f"{'s' if allowance.included_locations != 1 else ''}. "
                "Archive another location or choose a plan with more locations before turning this one on."
            ),
            reason_code="active_location_allowance_exhausted",
        )
        self.allowance = allowance
        self.requested_delta = requested_delta

    def safe_details(self) -> dict[str, Any]:
        required = _required_plan(self.allowance.plan_code)
        return {
            "message": str(self),
            "reason_code": self.reason_code,
            "plan_code": self.allowance.plan_code,
            "plan_name": self.allowance.plan_name,
            "included_locations": self.allowance.included_locations,
            "active_locations": self.allowance.active_locations,
            "remaining_locations": 0,
            "over_limit_by": self.allowance.over_limit_by,
            "required_plan_code": required[0] if required else None,
            "required_plan_name": required[1] if required else None,
        }


def get_active_location_allowance(
    db: Session,
    *,
    organization: Organization,
    lock_entitlement: bool = False,
) -> ActiveLocationAllowance:
    # Bootstrap and rolling-deploy repair are writes. Reacquire the canonical
    # organization lock even for summary callers so every path observes the
    # same Organization -> Entitlement lock order.
    organization = lock_organization_for_location_allowance(
        db,
        organization_id=organization.id,
    )
    plan_code = _normalized_plan_or_error(organization.plan_type)
    profile = db.get(TierProfile, organization.tier_profile_id)
    if profile is None or not profile.is_active:
        raise _configuration_error("The location allowance profile is unavailable.")
    if int(profile.version) != int(organization.tier_version):
        raise _configuration_error("The location allowance profile version does not match this account.")
    try:
        validate_commercial_profile_pointer(profile, plan_code=plan_code)
    except TierProfileValidationError as exc:
        raise _configuration_error(
            "The location allowance profile does not match a published account profile."
        ) from exc

    query = db.query(Entitlement).filter(
        Entitlement.organization_id == organization.id,
        Entitlement.code == LIMIT_ACTIVE_LOCATIONS,
    )
    query = query.populate_existing()
    if _supports_row_locking(db):
        query = query.with_for_update()
    entitlement = query.one_or_none()
    entitlement = _materialize_or_reconcile_allowance(
        db,
        organization=organization,
        plan_code=plan_code,
        entitlement=entitlement,
    )

    active_locations = int(
        db.query(func.count(BusinessLocation.id))
        .filter(
            BusinessLocation.organization_id == organization.id,
            BusinessLocation.status == "active",
        )
        .scalar()
        or 0
    )
    plan_name = COMMERCIAL_TIERS[plan_code].display_name
    capacity_enforced = _active_location_capacity_is_enforced(db)
    return ActiveLocationAllowance(
        organization_id=organization.id,
        plan_code=plan_code,
        plan_name=plan_name,
        tier_profile_id=profile.id,
        tier_version=int(profile.version),
        included_locations=int(entitlement.limit_value or 0),
        active_locations=active_locations,
        capacity_enforced=capacity_enforced,
    )


def lock_organization_for_location_allowance(
    db: Session,
    *,
    organization_id: str,
) -> Organization:
    query = (
        db.query(Organization)
        .filter(Organization.id == organization_id)
        .populate_existing()
    )
    if _supports_row_locking(db):
        query = query.with_for_update()
    organization = query.one_or_none()
    if organization is None:
        raise ActiveLocationAllowanceError(
            "Organization not found.",
            reason_code="organization_not_found",
        )
    return organization


def assert_active_location_capacity(
    db: Session,
    *,
    organization_id: str,
    requested_delta: int = 1,
    locked_organization: Organization | None = None,
) -> ActiveLocationAllowance:
    if requested_delta < 0:
        raise ValueError("requested_delta must be nonnegative")
    organization = locked_organization or lock_organization_for_location_allowance(
        db,
        organization_id=organization_id,
    )
    if organization.id != organization_id:
        raise ValueError("locked organization does not match organization_id")
    _assert_organization_active_for_commercial_work(organization)
    allowance = get_active_location_allowance(
        db,
        organization=organization,
        lock_entitlement=True,
    )
    if (
        allowance.capacity_enforced
        and allowance.active_locations + requested_delta > allowance.included_locations
    ):
        raise ActiveLocationAllowanceExceeded(
            allowance=allowance,
            requested_delta=requested_delta,
        )
    return allowance


def assert_provider_work_allowed(
    db: Session,
    *,
    organization_id: str,
    business_location_id: str | None = None,
    campaign_id: str | None = None,
    locked_organization: Organization | None = None,
) -> ActiveLocationAllowance:
    """Fail closed when a downgrade leaves more active locations than the plan covers."""
    organization = locked_organization or lock_organization_for_location_allowance(
        db, organization_id=organization_id
    )
    if organization.id != organization_id:
        raise ValueError("locked organization does not match organization_id")
    _assert_organization_active_for_commercial_work(organization)
    allowance = get_active_location_allowance(
        db,
        organization=organization,
        lock_entitlement=True,
    )
    if allowance.capacity_enforced and allowance.over_limit_by:
        raise ActiveLocationAllowanceError(
            (
                "Paid data updates are paused because this account has more active locations "
                "than its current plan includes. Archive locations or change plans to continue."
            ),
            reason_code="active_location_overage_blocks_provider_work",
        )
    if campaign_id is not None and business_location_id is None:
        raise ActiveLocationAllowanceError(
            (
                "This paid update must be connected to an active business location. "
                "Map the saved campaign to a location before running the update."
            ),
            reason_code="active_business_location_required_for_provider_work",
        )
    if business_location_id is not None:
        location_query = db.query(BusinessLocation).filter(
            BusinessLocation.id == business_location_id,
            BusinessLocation.organization_id == organization_id,
        )
        location_query = location_query.populate_existing()
        if _supports_row_locking(db):
            location_query = location_query.with_for_update()
        location = location_query.one_or_none()
        if location is None or location.status != "active":
            raise ActiveLocationAllowanceError(
                (
                    "Paid updates are available only for active locations on this account. "
                    "Turn this location back on before running the update."
                ),
                reason_code="active_business_location_required_for_provider_work",
            )
    if campaign_id is not None:
        campaign_query = db.query(Campaign).filter(
            Campaign.id == campaign_id,
            Campaign.organization_id == organization_id,
        )
        campaign_query = campaign_query.populate_existing()
        if _supports_row_locking(db):
            campaign_query = campaign_query.with_for_update()
        campaign = campaign_query.one_or_none()
        if campaign is None or campaign.business_location_id != business_location_id:
            raise ActiveLocationAllowanceError(
                (
                    "This paid update is not mapped to the selected active business location. "
                    "Correct the campaign location before running the update."
                ),
                reason_code="active_business_location_required_for_provider_work",
            )
    return allowance


def _materialize_or_reconcile_allowance(
    db: Session,
    *,
    organization: Organization,
    plan_code: str,
    entitlement: Entitlement | None,
) -> Entitlement:
    definition = COMMERCIAL_TIERS[plan_code]
    expected_limit = int(definition.active_location_limit)
    expected_config = {
        "catalog_version": COMMERCIAL_TIER_CATALOG_VERSION,
        "unit": "business_location",
    }
    now = datetime.now(UTC)
    if entitlement is None:
        entitlement = Entitlement(
            organization_id=organization.id,
            code=LIMIT_ACTIVE_LOCATIONS,
            value_type=EntitlementValueType.INTEGER,
            limit_value=expected_limit,
            reset_period=EntitlementResetPeriod.NONE,
            is_enforced=True,
            config_json=expected_config,
            deterministic_hash="",
            created_at=now,
            updated_at=now,
        )
        entitlement.deterministic_hash = _entitlement_hash(entitlement)
        db.add(entitlement)
        db.flush()
        return entitlement

    validate_canonical_bridge_entitlement(entitlement)
    if int(entitlement.limit_value or 0) != expected_limit:
        # A 0154 worker can change plan_type without knowing this row. Adopt
        # that ordered billing truth only when the existing row is itself a
        # valid canonical bridge value/hash for another published plan.
        entitlement.limit_value = expected_limit
        entitlement.deterministic_hash = _entitlement_hash(entitlement)
        entitlement.updated_at = now
        db.flush()
    return entitlement


def validate_canonical_bridge_entitlement(entitlement: Entitlement) -> None:
    expected_config = {
        "catalog_version": COMMERCIAL_TIER_CATALOG_VERSION,
        "unit": "business_location",
    }
    if (
        not entitlement.is_enforced
        or entitlement.value_type != EntitlementValueType.INTEGER
        or entitlement.reset_period != EntitlementResetPeriod.NONE
        or entitlement.limit_value is None
        or int(entitlement.limit_value)
        not in {definition.active_location_limit for definition in COMMERCIAL_TIERS.values()}
        or dict(entitlement.config_json or {}) != expected_config
    ):
        raise _configuration_error("The active-location allowance is not safely configured.")
    if entitlement.deterministic_hash != _entitlement_hash(entitlement):
        raise _configuration_error("The saved active-location allowance failed its integrity check.")


def _entitlement_hash(entitlement: Entitlement) -> str:
    payload = {
        "organization_id": entitlement.organization_id,
        "code": entitlement.code,
        "value_type": entitlement.value_type.value,
        "limit_value": entitlement.limit_value,
        "reset_period": entitlement.reset_period.value,
        "is_enforced": entitlement.is_enforced,
        "config_json": entitlement.config_json,
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(serialized.encode("utf-8")).hexdigest()


def _normalized_plan_or_error(plan_type: str) -> str:
    try:
        return normalize_commercial_plan_code(plan_type)
    except ValueError as exc:
        raise _configuration_error("This account does not have a supported location plan.") from exc


def _configuration_error(message: str) -> ActiveLocationAllowanceError:
    return ActiveLocationAllowanceError(
        message,
        reason_code="active_location_allowance_unavailable",
    )


def _assert_organization_active_for_commercial_work(
    organization: Organization,
) -> None:
    if str(organization.status or "").strip().lower() == "active":
        return
    raise ActiveLocationAllowanceError(
        (
            "New location and paid-data work is paused while this workspace is inactive. "
            "Restore the workspace before starting new work."
        ),
        reason_code="organization_inactive_for_commercial_work",
    )


def _required_plan(plan_code: str) -> tuple[str, str] | None:
    if plan_code == "solo":
        definition = COMMERCIAL_TIERS["multi_location"]
        return definition.code, definition.display_name
    if plan_code == "multi_location":
        definition = COMMERCIAL_TIERS["enterprise"]
        return definition.code, definition.display_name
    return None


def _active_location_capacity_is_enforced(db: Session) -> bool:
    bind = db.get_bind()
    if bind is None or not inspect(bind).has_table("commercial_feature_activations"):
        return False
    query = db.query(CommercialFeatureActivation).filter(
        CommercialFeatureActivation.code == ACTIVE_LOCATION_ACTIVATION_CODE
    ).populate_existing()
    if _supports_row_locking(db):
        # A future activation update cannot overtake a capacity/provider decision
        # already in flight. The shared row lock lasts through the caller's
        # transaction (and through immediate provider dispatch where applicable).
        query = query.with_for_update(read=True)
    row = query.one_or_none()
    if row is None:
        raise _configuration_error("The location allowance activation record is missing.")
    if row.catalog_version != COMMERCIAL_TIER_CATALOG_VERSION:
        raise _configuration_error("The location allowance activation catalog is invalid.")
    if row.state not in {ACTIVE_LOCATION_STATE_OBSERVE, ACTIVE_LOCATION_STATE_ENFORCED}:
        raise _configuration_error("The location allowance activation state is invalid.")
    return row.state == ACTIVE_LOCATION_STATE_ENFORCED


def _supports_row_locking(db: Session) -> bool:
    dialect = db.bind.dialect.name.lower() if db.bind is not None else ""
    return dialect in _LOCK_SUPPORTED_DIALECTS

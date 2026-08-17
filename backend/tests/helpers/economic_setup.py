from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.commercial_tiers import (
    COMMERCIAL_LEGACY_PROFILE_IDS,
    COMMERCIAL_LEGACY_TIER_VERSION,
    legacy_entitlement_template,
    legacy_tier_code_for_plan,
    normalize_commercial_plan_code,
)
from app.models.organization import Organization
from app.models.tier_profile import TierProfile
from app.services import provisioning_service
from app.services.commercial_plan_service import apply_commercial_plan
from app.services.tier_profile_service import compute_tier_profile_hash


def ensure_test_tier_profile(db: Session, *, plan_code: str = "enterprise") -> TierProfile:
    canonical_plan_code = normalize_commercial_plan_code(plan_code)
    legacy_tier_code = legacy_tier_code_for_plan(canonical_plan_code)
    entitlements = legacy_entitlement_template()["entitlements"]
    canonical_template = {
        "tier_code": legacy_tier_code,
        "version": COMMERCIAL_LEGACY_TIER_VERSION,
        "entitlements": entitlements,
    }
    deterministic_hash = compute_tier_profile_hash(canonical_template)

    tier_profile = (
        db.query(TierProfile)
        .filter(
            TierProfile.tier_code == legacy_tier_code,
            TierProfile.version == COMMERCIAL_LEGACY_TIER_VERSION,
        )
        .first()
    )
    if tier_profile is not None:
        return tier_profile

    tier_profile = TierProfile(
        id=COMMERCIAL_LEGACY_PROFILE_IDS[legacy_tier_code],
        tier_code=legacy_tier_code,
        display_name=legacy_tier_code.replace("_", " ").title(),
        version=COMMERCIAL_LEGACY_TIER_VERSION,
        entitlement_template_json={"entitlements": entitlements},
        deterministic_hash=deterministic_hash,
        is_active=True,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    try:
        with db.begin_nested():
            db.add(tier_profile)
            db.flush()
        return tier_profile
    except IntegrityError:
        tier_profile = (
            db.query(TierProfile)
            .filter(
                TierProfile.tier_code == legacy_tier_code,
                TierProfile.version == COMMERCIAL_LEGACY_TIER_VERSION,
            )
            .first()
        )
        if tier_profile is not None:
            return tier_profile
        raise


def provision_test_organization(
    db: Session,
    organization: Organization,
    *,
    plan_code: str = "enterprise",
) -> Organization:
    """
    Uses the rolling-deploy-compatible v1 pointer and materializes the real
    commercial allowance rather than bypassing production checks.
    """
    tier_profile = ensure_test_tier_profile(db, plan_code=plan_code)
    organization.tier_profile_id = tier_profile.id
    organization.tier_version = tier_profile.version
    organization.plan_type = plan_code
    organization.status = "active"
    db.flush()

    apply_commercial_plan(
        db,
        organization_id=organization.id,
        plan_code=plan_code,
    )

    provisioning_service.provision_organization(
        db,
        organization_id=organization.id,
        tier_profile_id=tier_profile.id,
    )
    db.refresh(organization)
    return organization

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.entitlement_codes import ALL_ENTITLEMENT_CODES
from app.models.organization import Organization
from app.models.tier_profile import TierProfile
from app.services import provisioning_service
from app.services.tier_profile_service import compute_tier_profile_hash


_TEST_TIER_CODE = "test_unlimited"
_TEST_TIER_VERSION = 1
_TEST_DISPLAY_NAME = "Test Unlimited"


def ensure_test_tier_profile(db: Session) -> TierProfile:
    entitlements = [
        {
            "code": code,
            "value_type": "unlimited",
            "limit_value": None,
            "reset_period": "none",
            "is_enforced": True,
            "config_json": {},
        }
        for code in sorted(ALL_ENTITLEMENT_CODES)
    ]
    canonical_template = {
        "tier_code": _TEST_TIER_CODE,
        "version": _TEST_TIER_VERSION,
        "entitlements": entitlements,
    }
    deterministic_hash = compute_tier_profile_hash(canonical_template)

    tier_profile = (
        db.query(TierProfile)
        .filter(TierProfile.deterministic_hash == deterministic_hash)
        .first()
    )
    if tier_profile is not None:
        return tier_profile

    tier_profile = TierProfile(
        id=str(uuid.uuid4()),
        tier_code=_TEST_TIER_CODE,
        display_name=_TEST_DISPLAY_NAME,
        version=_TEST_TIER_VERSION,
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
            .filter(TierProfile.deterministic_hash == deterministic_hash)
            .first()
        )
        if tier_profile is not None:
            return tier_profile
        raise


def provision_test_organization(db: Session, organization: Organization) -> Organization:
    """
    Creates a TierProfile with unlimited limits and provisions
    the organization so rank/crawl tests pass enforcement.
    """
    tier_profile = ensure_test_tier_profile(db)
    organization.tier_profile_id = tier_profile.id
    organization.tier_version = tier_profile.version
    organization.status = "active"
    db.flush()

    provisioning_service.provision_organization(
        db,
        organization_id=organization.id,
        tier_profile_id=tier_profile.id,
    )
    db.refresh(organization)
    return organization

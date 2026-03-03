from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
import json

from sqlalchemy.orm import Session

from app.models.onboarding_state import (
    ONBOARDING_STATE_ACTIVE,
    ONBOARDING_STATE_INIT,
    ONBOARDING_STATE_SUSPENDED,
    OnboardingState,
)
from app.models.organization import Organization
from app.services import provisioning_service


class OnboardingStateNotFoundError(Exception):
    pass


class MissingTierProfileReferenceError(Exception):
    pass



def start_onboarding(db: Session, organization_id: str, tier_profile_id: str) -> str:
    _require_organization(db, organization_id)
    _ensure_onboarding_state(db, organization_id=organization_id, state=ONBOARDING_STATE_INIT)
    result = provisioning_service.provision_organization(
        db,
        organization_id=organization_id,
        tier_profile_id=tier_profile_id,
    )
    return result.final_state



def get_onboarding_state(db: Session, organization_id: str) -> str:
    row = _load_onboarding_state(db, organization_id=organization_id)
    if row is None:
        raise OnboardingStateNotFoundError(f"OnboardingState not found for organization_id={organization_id}")
    return row.state



def resume_onboarding(db: Session, organization_id: str) -> str:
    organization = _require_organization(db, organization_id)
    if not organization.tier_profile_id:
        raise MissingTierProfileReferenceError(
            f"Organization missing tier_profile_id: {organization_id}"
        )
    _ensure_onboarding_state(db, organization_id=organization_id, state=ONBOARDING_STATE_INIT)
    result = provisioning_service.provision_organization(
        db,
        organization_id=organization_id,
        tier_profile_id=organization.tier_profile_id,
    )
    return result.final_state



def suspend_organization(db: Session, organization_id: str) -> str:
    _require_organization(db, organization_id)
    row = _ensure_onboarding_state(db, organization_id=organization_id, state=ONBOARDING_STATE_SUSPENDED)
    _transition_state(row, state=ONBOARDING_STATE_SUSPENDED)
    db.commit()
    return row.state



def activate_organization(db: Session, organization_id: str) -> str:
    _require_organization(db, organization_id)
    row = _ensure_onboarding_state(db, organization_id=organization_id, state=ONBOARDING_STATE_ACTIVE)
    _transition_state(row, state=ONBOARDING_STATE_ACTIVE)
    db.commit()
    return row.state



def _load_onboarding_state(db: Session, *, organization_id: str) -> OnboardingState | None:
    return (
        db.query(OnboardingState)
        .filter(OnboardingState.organization_id == organization_id)
        .first()
    )



def _ensure_onboarding_state(db: Session, *, organization_id: str, state: str) -> OnboardingState:
    row = _load_onboarding_state(db, organization_id=organization_id)
    if row is None:
        now = datetime.now(UTC)
        row = OnboardingState(
            organization_id=organization_id,
            state=state,
            last_transition_at=now,
            deterministic_hash=_state_hash(organization_id=organization_id, state=state),
        )
        db.add(row)
        db.flush()
    return row



def _transition_state(row: OnboardingState, *, state: str) -> None:
    if row.state == state:
        return
    now = datetime.now(UTC)
    row.state = state
    row.last_transition_at = now
    row.deterministic_hash = _state_hash(organization_id=row.organization_id, state=state)



def _require_organization(db: Session, organization_id: str) -> Organization:
    row = db.get(Organization, organization_id)
    if row is None:
        raise ValueError(f"Organization not found: {organization_id}")
    return row



def _state_hash(*, organization_id: str, state: str) -> str:
    payload = {
        "organization_id": organization_id,
        "state": state,
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return sha256(serialized.encode("utf-8")).hexdigest()

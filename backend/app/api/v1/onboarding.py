from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import require_org_role, require_roles
from app.api.response import envelope
from app.db.session import get_db
from app.schemas.onboarding import (
    OnboardingBaselineStatusOut,
    OnboardingSessionOut,
    OnboardingStartRequest,
)
from app.services import onboarding_baseline_service, onboarding_service


router = APIRouter(prefix="/onboarding", tags=["onboarding"])


@router.get("/baseline/{campaign_id}")
def get_onboarding_baseline(
    request: Request,
    campaign_id: str,
    user: dict = Depends(require_org_role({"org_user"})),
    db: Session = Depends(get_db),
) -> dict:
    payload = onboarding_baseline_service.get_status(
        db,
        tenant_id=str(user["tenant_id"]),
        organization_id=str(user["organization_id"]),
        campaign_id=campaign_id,
    )
    data = OnboardingBaselineStatusOut.model_validate(payload).model_dump(mode="json")
    return envelope(request, data)


@router.post("/baseline/{campaign_id}")
def ensure_onboarding_baseline(
    request: Request,
    campaign_id: str,
    user: dict = Depends(require_org_role({"org_user"})),
    db: Session = Depends(get_db),
) -> dict:
    payload = onboarding_baseline_service.ensure_baseline(
        db,
        tenant_id=str(user["tenant_id"]),
        organization_id=str(user["organization_id"]),
        campaign_id=campaign_id,
        generated_by_user_id=str(user["user_id"]),
    )
    data = OnboardingBaselineStatusOut.model_validate(payload).model_dump(mode="json")
    return envelope(request, data)


def _enforce_onboarding_session_scope(user: dict, row) -> None:
    if isinstance(user.get("platform_role"), str):
        return
    actor_scope = onboarding_service.get_onboarding_actor_scope(row)
    if actor_scope["user_id"] == user.get("id") and actor_scope["organization_id"] == user.get("organization_id"):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            "message": "Organization context does not match request scope.",
            "reason_code": "organization_scope_mismatch",
        },
    )


@router.post("/start")
def start_onboarding(
    request: Request,
    body: OnboardingStartRequest,
    user: dict = Depends(require_roles({"platform_owner", "platform_admin", "tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    row = onboarding_service.start_onboarding(
        db,
        body.model_dump(),
        actor_user_id=user["id"],
        actor_organization_id=user["organization_id"],
    )
    return envelope(request, OnboardingSessionOut.model_validate(row).model_dump(mode="json"))


@router.get("/status/{tenant_id}")
def get_onboarding_status(
    request: Request,
    tenant_id: str,
    user: dict = Depends(require_roles({"platform_owner", "platform_admin", "tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    row = onboarding_service.get_onboarding_status(db, tenant_id=tenant_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Onboarding session not found")
    _enforce_onboarding_session_scope(user, row)
    return envelope(request, OnboardingSessionOut.model_validate(row).model_dump(mode="json"))


@router.post("/resume/{tenant_id}")
def resume_onboarding(
    request: Request,
    tenant_id: str,
    user: dict = Depends(require_roles({"platform_owner", "platform_admin", "tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    row = onboarding_service.get_onboarding_status(db, tenant_id=tenant_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Onboarding session not found")
    _enforce_onboarding_session_scope(user, row)
    try:
        row = onboarding_service.resume_onboarding(db, tenant_id=tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return envelope(request, OnboardingSessionOut.model_validate(row).model_dump(mode="json"))

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import enforce_organization_scope, require_roles
from app.api.response import envelope
from app.db.session import get_db
from app.schemas.onboarding import OnboardingSessionOut, OnboardingStartRequest
from app.services import onboarding_service


router = APIRouter(prefix="/onboarding", tags=["onboarding"])


@router.post("/start")
def start_onboarding(
    request: Request,
    body: OnboardingStartRequest,
    _user: dict = Depends(require_roles({"platform_owner", "platform_admin", "tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    row = onboarding_service.start_onboarding(db, body.model_dump())
    return envelope(request, OnboardingSessionOut.model_validate(row).model_dump(mode="json"))


@router.get("/status/{tenant_id}")
def get_onboarding_status(
    request: Request,
    tenant_id: str,
    user: dict = Depends(require_roles({"platform_owner", "platform_admin", "tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    enforce_organization_scope(user=user, organization_id=tenant_id)
    row = onboarding_service.get_onboarding_status(db, tenant_id=tenant_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Onboarding session not found")
    return envelope(request, OnboardingSessionOut.model_validate(row).model_dump(mode="json"))


@router.post("/resume/{tenant_id}")
def resume_onboarding(
    request: Request,
    tenant_id: str,
    user: dict = Depends(require_roles({"platform_owner", "platform_admin", "tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    enforce_organization_scope(user=user, organization_id=tenant_id)
    try:
        row = onboarding_service.resume_onboarding(db, tenant_id=tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return envelope(request, OnboardingSessionOut.model_validate(row).model_dump(mode="json"))

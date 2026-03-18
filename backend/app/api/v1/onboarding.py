from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.api.response import envelope
from app.db.session import get_db
from app.schemas.onboarding import OnboardingSessionOut, OnboardingStartRequest
from app.services import onboarding_service


router = APIRouter(prefix="/onboarding", tags=["onboarding"])


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

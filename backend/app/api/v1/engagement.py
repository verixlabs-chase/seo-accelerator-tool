from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import require_org_role
from app.api.response import envelope
from app.db.session import get_db
from app.services import engagement_service


router = APIRouter(prefix="/engagement", tags=["engagement"])


class AchievementPreferenceIn(BaseModel):
    celebrations_enabled: bool | None = None
    notifications_enabled: bool | None = None


def _raise_engagement_error(exc: engagement_service.EngagementError) -> None:
    raise HTTPException(
        status_code=exc.status_code,
        detail={"message": str(exc), "reason_code": exc.reason_code},
    ) from exc


def _summary(
    *,
    request: Request,
    campaign_id: str,
    evaluate: bool,
    user: dict,
    db: Session,
) -> dict:
    try:
        payload = engagement_service.achievement_summary(
            db,
            tenant_id=user["tenant_id"],
            organization_id=user["organization_id"],
            user_id=user["id"],
            campaign_id=campaign_id,
            evaluate=evaluate,
        )
    except engagement_service.EngagementError as exc:
        _raise_engagement_error(exc)
    return envelope(request, payload)


@router.get("/achievements")
def get_achievements(
    request: Request,
    campaign_id: str = Query(..., min_length=1),
    user: dict = Depends(require_org_role({"org_user"})),
    db: Session = Depends(get_db),
) -> dict:
    return _summary(
        request=request,
        campaign_id=campaign_id,
        evaluate=False,
        user=user,
        db=db,
    )


@router.post("/achievements/evaluate")
def evaluate_achievements(
    request: Request,
    campaign_id: str = Query(..., min_length=1),
    user: dict = Depends(require_org_role({"org_user"})),
    db: Session = Depends(get_db),
) -> dict:
    return _summary(
        request=request,
        campaign_id=campaign_id,
        evaluate=True,
        user=user,
        db=db,
    )


@router.patch("/achievement-preferences")
def patch_achievement_preferences(
    request: Request,
    body: AchievementPreferenceIn,
    user: dict = Depends(require_org_role({"org_user"})),
    db: Session = Depends(get_db),
) -> dict:
    preferences = engagement_service.update_preferences(
        db,
        tenant_id=user["tenant_id"],
        organization_id=user["organization_id"],
        user_id=user["id"],
        celebrations_enabled=body.celebrations_enabled,
        notifications_enabled=body.notifications_enabled,
    )
    return envelope(request, {"preferences": preferences})

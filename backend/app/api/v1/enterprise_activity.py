from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.api.deps import require_org_role
from app.api.response import envelope
from app.db.session import get_db
from app.services import enterprise_activity_service
from app.services.cost_economics_service import CostEconomicsError


router = APIRouter(prefix="/enterprise/activity", tags=["enterprise-activity"])


@router.get("")
def get_enterprise_activity(
    request: Request,
    category: str | None = Query(default=None),
    cursor: str | None = Query(default=None, max_length=500),
    limit: int = Query(default=50, ge=1, le=100),
    user: dict = Depends(require_org_role({"org_owner"})),
    db: Session = Depends(get_db),
) -> dict:
    try:
        payload = enterprise_activity_service.list_organization_activity(
            db,
            tenant_id=str(user["tenant_id"]),
            organization_id=str(user["organization_id"]),
            requesting_user_id=str(user["id"]),
            category=category,
            cursor=cursor,
            limit=limit,
        )
    except (enterprise_activity_service.EnterpriseActivityError, CostEconomicsError) as exc:
        raise HTTPException(
            status_code=int(getattr(exc, "status_code", 400)),
            detail={
                "message": str(exc),
                "reason_code": str(
                    getattr(exc, "reason_code", "organization_activity_failed")
                ),
            },
        ) from exc
    return envelope(request, payload)

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.api.response import envelope
from app.db.session import get_db
from app.services import intelligence_service

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


@router.get("/summary")
def get_recommendation_summary(
    request: Request,
    campaign_id: str = Query(...),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    payload = intelligence_service.get_recommendation_summary(db, tenant_id=user["tenant_id"], campaign_id=campaign_id)
    return envelope(request, payload)

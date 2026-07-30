from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.api.response import envelope
from app.db.session import get_db
from app.models.campaign import Campaign
from app.services import durable_job_service, website_performance_service


router = APIRouter(prefix="/website-performance", tags=["website-performance"])


def _tenant_campaign(db: Session, *, tenant_id: str, campaign_id: str) -> Campaign:
    campaign = (
        db.query(Campaign)
        .filter(
            Campaign.id == campaign_id,
            Campaign.tenant_id == tenant_id,
        )
        .first()
    )
    if campaign is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business website not found.",
        )
    return campaign


@router.get("/summary")
def get_website_performance_summary(
    request: Request,
    campaign_id: str = Query(min_length=1),
    form_factor: str = Query(default="mobile", pattern="^(mobile|desktop)$"),
    days: int = Query(default=90, ge=7, le=730),
    user: dict = Depends(require_roles({"org_user"})),
    db: Session = Depends(get_db),
) -> dict:
    _tenant_campaign(db, tenant_id=user["tenant_id"], campaign_id=campaign_id)
    return envelope(
        request,
        website_performance_service.get_campaign_performance_summary(
            db,
            tenant_id=user["tenant_id"],
            campaign_id=campaign_id,
            form_factor=form_factor,
            days=days,
        ),
    )


@router.post("/collect")
def collect_website_performance(
    request: Request,
    campaign_id: str = Query(min_length=1),
    form_factor: str = Query(default="mobile", pattern="^(mobile|desktop)$"),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    _tenant_campaign(db, tenant_id=user["tenant_id"], campaign_id=campaign_id)
    try:
        result = durable_job_service.run_website_performance_job_now(
            db,
            tenant_id=user["tenant_id"],
            campaign_id=campaign_id,
            form_factor=form_factor,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    return envelope(request, result)


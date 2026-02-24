from __future__ import annotations

import uuid
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.api.response import envelope
from app.db.session import get_db
from app.models.campaign import Campaign
from app.models.organization import Organization
from app.services import fleet_service


router = APIRouter(prefix="/debug", tags=["debug"])


@router.post("/live-gsc-test")
def debug_live_gsc_test(
    request: Request,
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    organization_id = user.get("organization_id")
    if not isinstance(organization_id, str) or not organization_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Organization context required")
    organization = db.get(Organization, organization_id)
    if organization is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

    campaign = (
        db.query(Campaign)
        .filter(
            Campaign.tenant_id == organization.id,
            Campaign.portfolio_id.isnot(None),
        )
        .order_by(Campaign.created_at.asc())
        .first()
    )
    if campaign is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No campaign with portfolio_id found")
    if campaign.portfolio_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign missing portfolio_id")

    fleet_job_id = fleet_service.create_onboard_job(
        db=db,
        organization_id=str(organization.id),
        portfolio_id=str(campaign.portfolio_id),
        user_id=None,
        idempotency_key=f"debug-live-gsc-{uuid.uuid4()}",
        item_seeds=[
            {
                "item_key": f"debug-live-gsc-{campaign.id}",
                "payload": {
                    "provider_call": "google_search_console_query",
                    "campaign_id": str(campaign.id),
                    "site_url": f"https://{campaign.domain}",
                    "start_date": "2024-01-01",
                    "end_date": "2024-01-07",
                    "dimensions": ["query"],
                    "row_limit": 5,
                },
            }
        ],
    )

    return envelope(
        request,
        {
            "fleet_job_id": fleet_job_id,
            "campaign_id": str(campaign.id),
            "portfolio_id": str(campaign.portfolio_id),
        },
    )


@router.post("/test-gsc-validation")
def debug_test_gsc_validation(
    request: Request,
    user: dict = Depends(require_roles({"tenant_admin"})),
) -> dict:
    organization_id = user.get("organization_id")
    if not isinstance(organization_id, str) or not organization_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Organization context required")
    try:
        org_uuid = UUID(organization_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid organization_id") from exc
    try:
        result = fleet_service.test_gsc_fleet_validation(org_uuid)
    except fleet_service.FleetSearchConsoleValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.as_payload()) from exc
    return envelope(request, result)

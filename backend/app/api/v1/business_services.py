from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.api.response import envelope
from app.db.session import get_db
from app.schemas.business_service import (
    BusinessServiceCreateIn,
    BusinessServiceDiscoverIn,
    BusinessServicePatchIn,
)
from app.services import business_service_service
from app.services import keyword_research_service


router = APIRouter(prefix="/business-services", tags=["business-services"])


@router.get("")
def get_business_services(
    request: Request,
    campaign_id: str = Query(..., min_length=1, max_length=36),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    payload = business_service_service.get_profile(
        db,
        tenant_id=user["tenant_id"],
        campaign_id=campaign_id,
    )
    return envelope(request, payload)


@router.post("")
def add_business_service(
    request: Request,
    body: BusinessServiceCreateIn,
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    payload = business_service_service.add_manual_service(
        db,
        tenant_id=user["tenant_id"],
        campaign_id=body.campaign_id,
        name=body.name,
    )
    keyword_research_service.reclassify_latest(
        db, tenant_id=user["tenant_id"], campaign_id=body.campaign_id
    )
    payload = business_service_service.get_profile(
        db, tenant_id=user["tenant_id"], campaign_id=body.campaign_id
    )
    return envelope(request, payload)


@router.post("/discover")
def discover_business_services(
    request: Request,
    body: BusinessServiceDiscoverIn,
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    payload = business_service_service.discover_from_website(
        db,
        tenant_id=user["tenant_id"],
        campaign_id=body.campaign_id,
    )
    keyword_research_service.reclassify_latest(
        db, tenant_id=user["tenant_id"], campaign_id=body.campaign_id
    )
    return envelope(request, payload)


@router.patch("/{service_id}")
def patch_business_service(
    request: Request,
    service_id: str,
    body: BusinessServicePatchIn,
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    payload = business_service_service.review_service(
        db,
        tenant_id=user["tenant_id"],
        campaign_id=body.campaign_id,
        service_id=service_id,
        next_status=body.status,
    )
    keyword_research_service.reclassify_latest(
        db, tenant_id=user["tenant_id"], campaign_id=body.campaign_id
    )
    payload = business_service_service.get_profile(
        db, tenant_id=user["tenant_id"], campaign_id=body.campaign_id
    )
    return envelope(request, payload)

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.api.response import envelope
from app.db.session import get_db
from app.schemas.business_service_area import (
    BusinessServiceAreaCreateIn,
    BusinessServiceAreaPatchIn,
    BusinessServiceAreaSuggestIn,
)
from app.services import business_service_area_service, keyword_research_service


router = APIRouter(prefix="/business-service-areas", tags=["business-service-areas"])


@router.get("")
def get_business_service_areas(
    request: Request,
    campaign_id: str = Query(..., min_length=1, max_length=36),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    return envelope(
        request,
        business_service_area_service.get_profile(
            db, tenant_id=user["tenant_id"], campaign_id=campaign_id
        ),
    )


@router.post("")
def add_business_service_area(
    request: Request,
    body: BusinessServiceAreaCreateIn,
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    business_service_area_service.add_manual_area(
        db,
        tenant_id=user["tenant_id"],
        campaign_id=body.campaign_id,
        area_type=body.area_type,
        name=body.name,
        region=body.region,
        country_code=body.country_code,
        radius_miles=body.radius_miles,
        relationship=body.relationship,
    )
    keyword_research_service.reclassify_latest(
        db, tenant_id=user["tenant_id"], campaign_id=body.campaign_id
    )
    return envelope(
        request,
        business_service_area_service.get_profile(
            db, tenant_id=user["tenant_id"], campaign_id=body.campaign_id
        ),
    )


@router.post("/suggest")
def suggest_business_service_areas(
    request: Request,
    body: BusinessServiceAreaSuggestIn,
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    payload = business_service_area_service.suggest_areas(
        db, tenant_id=user["tenant_id"], campaign_id=body.campaign_id
    )
    keyword_research_service.reclassify_latest(
        db, tenant_id=user["tenant_id"], campaign_id=body.campaign_id
    )
    return envelope(request, payload)


@router.patch("/{area_id}")
def patch_business_service_area(
    request: Request,
    area_id: str,
    body: BusinessServiceAreaPatchIn,
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    business_service_area_service.review_area(
        db,
        tenant_id=user["tenant_id"],
        campaign_id=body.campaign_id,
        area_id=area_id,
        next_status=body.status,
    )
    keyword_research_service.reclassify_latest(
        db, tenant_id=user["tenant_id"], campaign_id=body.campaign_id
    )
    return envelope(
        request,
        business_service_area_service.get_profile(
            db, tenant_id=user["tenant_id"], campaign_id=body.campaign_id
        ),
    )

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from kombu.exceptions import KombuError
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.api.response import envelope
from app.db.session import get_db
from app.models.content import ContentAsset
from app.schemas.content import ContentAssetCreateIn, ContentAssetOut, ContentAssetUpdateIn
from app.services import content_service, infra_service
from app.tasks.tasks import content_generate_plan, content_refresh_internal_link_map, content_run_qc_checks

content_router = APIRouter(prefix="/content", tags=["content"])
internal_links_router = APIRouter(prefix="/internal-links", tags=["internal-links"])


@content_router.post("/assets")
def create_content_asset(
    request: Request,
    body: ContentAssetCreateIn,
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    asset = content_service.create_asset(
        db,
        tenant_id=user["tenant_id"],
        campaign_id=body.campaign_id,
        cluster_name=body.cluster_name,
        title=body.title,
        planned_month=body.planned_month,
    )
    return envelope(request, ContentAssetOut.model_validate(asset).model_dump(mode="json"))


@content_router.patch("/assets/{asset_id}")
def update_content_asset(
    request: Request,
    asset_id: str,
    body: ContentAssetUpdateIn,
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    before = db.get(ContentAsset, asset_id)
    before_status = before.status if before else None
    asset = content_service.update_asset(
        db,
        tenant_id=user["tenant_id"],
        asset_id=asset_id,
        status_value=body.status,
        title=body.title,
        target_url=body.target_url,
    )
    if before_status != "published" and asset.status == "published":
        try:
            content_run_qc_checks.delay(tenant_id=user["tenant_id"], asset_id=asset.id)
            content_refresh_internal_link_map.delay(tenant_id=user["tenant_id"], campaign_id=asset.campaign_id)
        except KombuError:
            pass
    return envelope(request, ContentAssetOut.model_validate(asset).model_dump(mode="json"))


@content_router.get("/plan")
def get_content_plan(
    request: Request,
    campaign_id: str = Query(...),
    month_number: int = Query(default=1),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    if infra_service.queue_backpressure_active("content"):
        raise HTTPException(
            status_code=503,
            detail={"message": "System under load", "reason_code": "queue_backpressure_active"},
        )
    try:
        task = content_generate_plan.delay(tenant_id=user["tenant_id"], campaign_id=campaign_id, month_number=month_number)
    except KombuError:
        task = None
    items = content_service.get_plan(db, tenant_id=user["tenant_id"], campaign_id=campaign_id, month_number=month_number)
    return envelope(
        request,
        {
            "job_id": task.id if task is not None else None,
            "items": [ContentAssetOut.model_validate(i).model_dump(mode="json") for i in items],
        },
    )


@internal_links_router.get("/recommendations")
def get_internal_link_recommendations(
    request: Request,
    campaign_id: str = Query(...),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    content_service.refresh_internal_link_map(db, tenant_id=user["tenant_id"], campaign_id=campaign_id)
    items = content_service.get_link_recommendations(db, tenant_id=user["tenant_id"], campaign_id=campaign_id)
    return envelope(request, {"items": items})

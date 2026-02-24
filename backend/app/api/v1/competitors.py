from fastapi import APIRouter, Depends, Query, Request
from kombu.exceptions import KombuError
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.api.response import envelope
from app.db.session import get_db
from app.schemas.competitor import CompetitorCreateIn, CompetitorOut
from app.services import competitor_service
from app.tasks.tasks import competitor_collect_snapshot

router = APIRouter(prefix="/competitors", tags=["competitors"])


@router.post("")
def create_competitor(
    request: Request,
    body: CompetitorCreateIn,
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    item = competitor_service.create_competitor(
        db,
        tenant_id=user["tenant_id"],
        campaign_id=body.campaign_id,
        domain=body.domain,
        label=body.label,
    )
    return envelope(request, CompetitorOut.model_validate(item).model_dump(mode="json"))


@router.get("")
def get_competitors(
    request: Request,
    campaign_id: str = Query(...),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    items = competitor_service.list_competitors(db, tenant_id=user["tenant_id"], campaign_id=campaign_id)
    return envelope(request, {"items": [CompetitorOut.model_validate(i).model_dump(mode="json") for i in items]})


@router.get("/snapshots")
def get_snapshots(
    request: Request,
    campaign_id: str = Query(...),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    try:
        task = competitor_collect_snapshot.delay(campaign_id=campaign_id, tenant_id=user["tenant_id"])
    except KombuError:
        task = None
    snapshots = competitor_service.list_snapshots(db, tenant_id=user["tenant_id"], campaign_id=campaign_id)
    return envelope(request, {"job_id": task.id if task is not None else None, "items": snapshots})


@router.get("/gaps")
def get_gaps(
    request: Request,
    campaign_id: str = Query(...),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    gaps = competitor_service.compute_gaps(db, tenant_id=user["tenant_id"], campaign_id=campaign_id)
    return envelope(request, {"items": gaps})

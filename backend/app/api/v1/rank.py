from fastapi import APIRouter, Depends, Query, Request
from kombu.exceptions import KombuError
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.api.response import envelope
from app.db.session import get_db
from app.schemas.rank import RankingSnapshotOut, RankKeywordIn, RankScheduleIn
from app.services import rank_service
from app.tasks.tasks import rank_schedule_window

router = APIRouter(prefix="/rank", tags=["rank"])


@router.post("/keywords")
def add_keyword(
    request: Request,
    body: RankKeywordIn,
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    item = rank_service.add_keyword(
        db,
        tenant_id=user["tenant_id"],
        campaign_id=body.campaign_id,
        cluster_name=body.cluster_name,
        keyword=body.keyword,
        location_code=body.location_code,
    )
    return envelope(
        request,
        {
            "id": item.id,
            "campaign_id": item.campaign_id,
            "keyword": item.keyword,
            "location_code": item.location_code,
        },
    )


@router.post("/schedule")
def schedule_rank_collection(
    request: Request,
    body: RankScheduleIn,
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    payload = rank_service.run_snapshot_collection(
        db,
        tenant_id=user["tenant_id"],
        campaign_id=body.campaign_id,
        location_code=body.location_code,
    )
    try:
        rank_schedule_window.delay(campaign_id=body.campaign_id, tenant_id=user["tenant_id"], location_code=body.location_code)
    except KombuError:
        pass
    return envelope(request, payload)


@router.get("/snapshots")
def get_rank_snapshots(
    request: Request,
    campaign_id: str = Query(...),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    rows = rank_service.get_snapshots(db, tenant_id=user["tenant_id"], campaign_id=campaign_id)
    return envelope(request, {"items": [RankingSnapshotOut.model_validate(r).model_dump(mode="json") for r in rows]})


@router.get("/trends")
def get_rank_trends(
    request: Request,
    campaign_id: str = Query(...),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    trends = rank_service.get_trends(db, tenant_id=user["tenant_id"], campaign_id=campaign_id)
    return envelope(request, {"items": trends})


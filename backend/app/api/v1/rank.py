from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.api.response import envelope
from app.db.session import get_db
from app.models.campaign import Campaign
from app.schemas.rank import RankingSnapshotOut, RankKeywordIn, RankScheduleIn
from app.services import rank_service
from app.tasks.tasks import rank_schedule_window

router = APIRouter(prefix="/rank", tags=["rank"])


def _dispatch_rank_schedule(campaign_id: str, tenant_id: str, location_code: str) -> None:
    try:
        rank_schedule_window.delay(campaign_id=campaign_id, tenant_id=tenant_id, location_code=location_code)
    except Exception:
        return


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
    background_tasks: BackgroundTasks,
    body: RankScheduleIn,
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    campaign = db.get(Campaign, body.campaign_id)
    if campaign is None or campaign.tenant_id != user["tenant_id"]:
        raise HTTPException(status_code=404, detail="Campaign not found")
    tracked_keywords = rank_service.get_tracked_keyword_count(db, tenant_id=user["tenant_id"], campaign_id=body.campaign_id)
    try:
        payload = rank_service.run_snapshot_collection(
            db,
            tenant_id=user["tenant_id"],
            campaign_id=body.campaign_id,
            location_code=body.location_code,
        )
    except HTTPException as exc:
        truth = rank_service.build_rank_truth(
            db,
            organization_id=campaign.organization_id,
            tracked_keywords=tracked_keywords,
            snapshot_count=0,
        )
        exc.detail = {
            **(exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}),
            "truth": truth,
        }
        raise
    background_tasks.add_task(_dispatch_rank_schedule, body.campaign_id, user["tenant_id"], body.location_code)
    truth = rank_service.build_rank_truth(
        db,
        organization_id=campaign.organization_id,
        tracked_keywords=tracked_keywords,
        snapshot_count=int(payload.get("snapshots_created", 0)),
        job_queued=True,
    )
    return envelope(request, {**payload, "truth": truth})


@router.get("/snapshots")
def get_rank_snapshots(
    request: Request,
    campaign_id: str = Query(...),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None or campaign.tenant_id != user["tenant_id"]:
        raise HTTPException(status_code=404, detail="Campaign not found")
    rows = rank_service.get_snapshots(db, tenant_id=user["tenant_id"], campaign_id=campaign_id)
    items = [RankingSnapshotOut.model_validate(r).model_dump(mode="json") for r in rows]
    truth = rank_service.build_rank_truth(
        db,
        organization_id=campaign.organization_id,
        tracked_keywords=rank_service.get_tracked_keyword_count(db, tenant_id=user["tenant_id"], campaign_id=campaign_id),
        snapshot_count=len(items),
        latest_captured_at=items[0]["captured_at"] if items else None,
    )
    return envelope(request, {"items": items, "truth": truth})


@router.get("/trends")
def get_rank_trends(
    request: Request,
    campaign_id: str = Query(...),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None or campaign.tenant_id != user["tenant_id"]:
        raise HTTPException(status_code=404, detail="Campaign not found")
    trends = rank_service.get_trends(db, tenant_id=user["tenant_id"], campaign_id=campaign_id)
    snapshots = rank_service.get_snapshots(db, tenant_id=user["tenant_id"], campaign_id=campaign_id)
    truth = rank_service.build_rank_truth(
        db,
        organization_id=campaign.organization_id,
        tracked_keywords=rank_service.get_tracked_keyword_count(db, tenant_id=user["tenant_id"], campaign_id=campaign_id),
        snapshot_count=len(snapshots),
        latest_captured_at=snapshots[0].captured_at.isoformat() if snapshots else None,
    )
    latest_captured_at = snapshots[0].captured_at.isoformat() if snapshots else None
    return envelope(
        request,
        {
            "items": trends,
            "latest_captured_at": latest_captured_at,
            "tracked_keywords": rank_service.get_tracked_keyword_count(db, tenant_id=user["tenant_id"], campaign_id=campaign_id),
            "truth": truth,
        },
    )

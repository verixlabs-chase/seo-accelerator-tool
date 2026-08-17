from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query, Request
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.api.response import envelope
from app.db.session import get_db
from app.models.campaign import Campaign
from app.schemas.rank import RankingSnapshotOut, RankKeywordBulkIn, RankKeywordIn, RankScheduleIn
from app.services import rank_service

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


@router.post("/keywords/bulk")
def add_keywords_bulk(
    request: Request,
    body: RankKeywordBulkIn,
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    result = rank_service.add_keywords_bulk(
        db,
        tenant_id=user["tenant_id"],
        campaign_id=body.campaign_id,
        cluster_name=body.cluster_name,
        keywords=body.keywords,
        location_code=body.location_code,
    )
    return envelope(
        request,
        {
            "created": [
                {
                    "id": item.id,
                    "campaign_id": item.campaign_id,
                    "keyword": item.keyword,
                    "location_code": item.location_code,
                }
                for item in result["created"]
            ],
            "created_count": len(result["created"]),
            "skipped_count": len(result["skipped"]),
            "location_code": result["location_code"],
        },
    )


@router.get("/keywords")
def get_keywords(
    request: Request,
    campaign_id: str = Query(...),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    items = rank_service.list_keywords(db, tenant_id=user["tenant_id"], campaign_id=campaign_id)
    return envelope(request, {"items": items, "count": len(items)})


@router.delete("/keywords/{keyword_id}")
def delete_keyword(
    request: Request,
    keyword_id: str,
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    rank_service.delete_keyword(db, tenant_id=user["tenant_id"], keyword_id=keyword_id)
    return envelope(request, {"deleted": True, "keyword_id": keyword_id})


@router.get("/portfolio")
def get_rank_portfolio(
    request: Request,
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    return envelope(request, rank_service.get_portfolio_summary(db, tenant_id=user["tenant_id"]))


@router.post("/schedule")
def schedule_rank_collection(
    request: Request,
    body: RankScheduleIn,
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    campaign = db.get(Campaign, body.campaign_id)
    if campaign is None or campaign.tenant_id != user["tenant_id"]:
        raise HTTPException(status_code=404, detail="Campaign not found")
    location_code = rank_service.resolve_location_code(
        db,
        tenant_id=user["tenant_id"],
        campaign_id=body.campaign_id,
        requested_location_code=body.location_code,
    )
    tracked_keywords = rank_service.get_tracked_keyword_count(db, tenant_id=user["tenant_id"], campaign_id=body.campaign_id)
    try:
        payload = rank_service.run_snapshot_collection(
            db,
            tenant_id=user["tenant_id"],
            campaign_id=body.campaign_id,
            location_code=location_code,
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
    truth = rank_service.build_rank_truth(
        db,
        organization_id=campaign.organization_id,
        tracked_keywords=tracked_keywords,
        snapshot_count=int(payload.get("snapshots_created", 0)),
        latest_captured_at=datetime.now(UTC) if payload.get("snapshots_created") else None,
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
    collected_items = [item for item in items if item["source_type"] != "imported"]
    imported_history_count = len(items) - len(collected_items)
    truth = rank_service.build_rank_truth(
        db,
        organization_id=campaign.organization_id,
        tracked_keywords=rank_service.get_tracked_keyword_count(db, tenant_id=user["tenant_id"], campaign_id=campaign_id),
        snapshot_count=len(collected_items),
        latest_captured_at=collected_items[0]["captured_at"] if collected_items else None,
    )
    return envelope(
        request,
        {
            "items": items,
            "imported_history_count": imported_history_count,
            "history_notice": (
                "Imported points preserve their original dates and are separate from live checks."
                if imported_history_count
                else None
            ),
            "truth": truth,
        },
    )


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
    collected_snapshots = [row for row in snapshots if row.source_type != "imported"]
    truth = rank_service.build_rank_truth(
        db,
        organization_id=campaign.organization_id,
        tracked_keywords=rank_service.get_tracked_keyword_count(db, tenant_id=user["tenant_id"], campaign_id=campaign_id),
        snapshot_count=len(collected_snapshots),
        latest_captured_at=(
            collected_snapshots[0].captured_at.isoformat() if collected_snapshots else None
        ),
    )
    latest_captured_at = (
        collected_snapshots[0].captured_at.isoformat() if collected_snapshots else None
    )
    return envelope(
        request,
        {
            "items": trends,
            "latest_captured_at": latest_captured_at,
            "tracked_keywords": rank_service.get_tracked_keyword_count(db, tenant_id=user["tenant_id"], campaign_id=campaign_id),
            "imported_history_count": len(snapshots) - len(collected_snapshots),
            "truth": truth,
        },
    )

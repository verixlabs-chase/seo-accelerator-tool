from fastapi import APIRouter, Depends, Query, Request
from kombu.exceptions import KombuError
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.api.response import envelope
from app.db.session import get_db
from app.schemas.crawl import CrawlRunOut, CrawlScheduleRequest, TechnicalIssueOut
from app.services import crawl_service
from app.tasks.tasks import crawl_schedule_campaign

router = APIRouter(prefix="/crawl", tags=["crawl"])


@router.post("/schedule")
def schedule_crawl(
    request: Request,
    body: CrawlScheduleRequest,
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    run = crawl_service.schedule_crawl(
        db,
        tenant_id=user["tenant_id"],
        campaign_id=body.campaign_id,
        crawl_type=body.crawl_type,
        seed_url=body.seed_url,
    )
    try:
        crawl_schedule_campaign.delay(campaign_id=run.campaign_id, crawl_run_id=run.id, tenant_id=run.tenant_id)
    except KombuError:
        pass
    return envelope(request, CrawlRunOut.model_validate(run).model_dump(mode="json"))


@router.get("/runs")
def get_runs(
    request: Request,
    campaign_id: str | None = Query(default=None),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    runs = crawl_service.list_runs(db, tenant_id=user["tenant_id"], campaign_id=campaign_id)
    return envelope(request, {"items": [CrawlRunOut.model_validate(r).model_dump(mode="json") for r in runs]})


@router.get("/issues")
def get_issues(
    request: Request,
    campaign_id: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    issues = crawl_service.list_issues(db, tenant_id=user["tenant_id"], campaign_id=campaign_id, severity=severity)
    return envelope(request, {"items": [TechnicalIssueOut.model_validate(i).model_dump(mode="json") for i in issues]})

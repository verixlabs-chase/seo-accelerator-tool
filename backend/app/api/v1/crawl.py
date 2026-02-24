from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.api.response import envelope
from app.db.session import SessionLocal, get_db
from app.schemas.crawl import CrawlRunOut, CrawlRunProgressOut, CrawlScheduleRequest, TechnicalIssueOut
from app.services import crawl_metrics, crawl_service, infra_service
from app.tasks.tasks import crawl_schedule_campaign

router = APIRouter(prefix="/crawl", tags=["crawl"])


def _dispatch_crawl_schedule(campaign_id: str, crawl_run_id: str, tenant_id: str) -> None:
    try:
        crawl_schedule_campaign.delay(campaign_id=campaign_id, crawl_run_id=crawl_run_id, tenant_id=tenant_id)
    except Exception:
        db = SessionLocal()
        try:
            crawl_service.execute_run(db, crawl_run_id=crawl_run_id)
        except Exception as exc:
            crawl_service.mark_run_failed(db, crawl_run_id, str(exc))
        finally:
            db.close()


@router.post("/schedule")
def schedule_crawl(
    request: Request,
    background_tasks: BackgroundTasks,
    body: CrawlScheduleRequest,
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    if infra_service.queue_backpressure_active("crawl"):
        return JSONResponse(
            status_code=503,
            content=envelope(
                request,
                data=None,
                error={
                    "message": "System under load",
                    "details": {"reason_code": "queue_backpressure_active"},
                },
            ),
        )
    run = crawl_service.schedule_crawl(
        db,
        tenant_id=user["tenant_id"],
        campaign_id=body.campaign_id,
        crawl_type=body.crawl_type,
        seed_url=body.seed_url,
    )
    background_tasks.add_task(_dispatch_crawl_schedule, run.campaign_id, run.id, run.tenant_id)
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


@router.get("/runs/{crawl_run_id}/progress")
def get_run_progress(
    request: Request,
    crawl_run_id: str,
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    progress = crawl_service.get_run_progress(db, tenant_id=user["tenant_id"], crawl_run_id=crawl_run_id)
    return envelope(request, CrawlRunProgressOut.model_validate(progress).model_dump(mode="json"))


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


@router.get("/metrics")
def get_crawl_metrics(
    request: Request,
    user: dict = Depends(require_roles({"tenant_admin"})),
) -> dict:
    _ = user
    return envelope(request, crawl_metrics.snapshot())

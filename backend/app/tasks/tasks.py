import json
from datetime import UTC, datetime

from app.tasks.celery_app import celery_app


@celery_app.task(name="ops.healthcheck.snapshot")
def ops_healthcheck_snapshot() -> dict:
    return {"timestamp": datetime.now(UTC).isoformat(), "status": "ok"}


@celery_app.task(name="campaigns.bootstrap_month_plan")
def campaigns_bootstrap_month_plan(campaign_id: str, tenant_id: str) -> dict:
    return {"campaign_id": campaign_id, "tenant_id": tenant_id, "month_number": 1, "status": "bootstrapped"}


@celery_app.task(name="audit.write_event")
def audit_write_event(event_type: str, tenant_id: str, actor_user_id: str | None = None, payload: dict | None = None) -> str:
    return json.dumps(
        {
            "event_type": event_type,
            "tenant_id": tenant_id,
            "actor_user_id": actor_user_id,
            "payload": payload or {},
        }
    )


@celery_app.task(name="crawl.schedule_campaign")
def crawl_schedule_campaign(campaign_id: str, crawl_run_id: str, tenant_id: str) -> dict:
    return {"campaign_id": campaign_id, "crawl_run_id": crawl_run_id, "tenant_id": tenant_id, "status": "scheduled"}


@celery_app.task(name="crawl.fetch_batch")
def crawl_fetch_batch(crawl_run_id: str, batch_urls: list[str]) -> dict:
    return {"crawl_run_id": crawl_run_id, "url_count": len(batch_urls)}


@celery_app.task(name="crawl.parse_page")
def crawl_parse_page(crawl_run_id: str, url: str, html: str) -> dict:
    return {"crawl_run_id": crawl_run_id, "url": url, "html_size": len(html)}


@celery_app.task(name="crawl.extract_issues")
def crawl_extract_issues(crawl_run_id: str, page_result_id: str) -> dict:
    return {"crawl_run_id": crawl_run_id, "page_result_id": page_result_id, "issues_found": 0}


@celery_app.task(name="crawl.finalize_run")
def crawl_finalize_run(crawl_run_id: str) -> dict:
    return {"crawl_run_id": crawl_run_id, "status": "complete"}

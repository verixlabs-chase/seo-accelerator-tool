import json
from datetime import UTC, datetime

from app.db.session import SessionLocal
from app.models.crawl import CrawlPageResult
from app.services import crawl_service
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


@celery_app.task(name="crawl.schedule_campaign", bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def crawl_schedule_campaign(self, campaign_id: str, crawl_run_id: str, tenant_id: str) -> dict:
    db = SessionLocal()
    try:
        run = crawl_service.get_run_or_404(db, crawl_run_id)
        urls = crawl_service.build_batch_urls(run.seed_url, run.crawl_type)
        crawl_fetch_batch.delay(crawl_run_id=crawl_run_id, batch_urls=urls)
        return {"campaign_id": campaign_id, "crawl_run_id": crawl_run_id, "tenant_id": tenant_id, "status": "queued"}
    except Exception as exc:
        crawl_service.mark_run_failed(db, crawl_run_id, str(exc))
        raise
    finally:
        db.close()


@celery_app.task(name="crawl.fetch_batch", bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def crawl_fetch_batch(self, crawl_run_id: str, batch_urls: list[str]) -> dict:
    db = SessionLocal()
    try:
        return crawl_service.execute_run(db, crawl_run_id=crawl_run_id, provided_urls=batch_urls)
    except Exception as exc:
        crawl_service.mark_run_failed(db, crawl_run_id, str(exc))
        raise
    finally:
        db.close()


@celery_app.task(name="crawl.parse_page", bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def crawl_parse_page(self, crawl_run_id: str, url: str, html: str, status_code: int | None = 200) -> dict:
    db = SessionLocal()
    try:
        run = crawl_service.get_run_or_404(db, crawl_run_id)
        result = crawl_service.record_page_result(db, run, url=url, status_code=status_code, html=html)
        db.commit()
        return {"crawl_run_id": crawl_run_id, "url": url, "page_result_id": result.id}
    except Exception as exc:
        crawl_service.mark_run_failed(db, crawl_run_id, str(exc))
        raise
    finally:
        db.close()


@celery_app.task(name="crawl.extract_issues", bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def crawl_extract_issues(self, crawl_run_id: str, page_result_id: str) -> dict:
    db = SessionLocal()
    try:
        run = crawl_service.get_run_or_404(db, crawl_run_id)
        result = (
            db.query(CrawlPageResult)
            .filter(CrawlPageResult.id == page_result_id, CrawlPageResult.crawl_run_id == crawl_run_id)
            .first()
        )
        if result is None:
            return {"crawl_run_id": crawl_run_id, "page_result_id": page_result_id, "issues_found": 0}
        issues = crawl_service.extract_issues_for_result(db, run, result)
        db.commit()
        return {"crawl_run_id": crawl_run_id, "page_result_id": page_result_id, "issues_found": len(issues)}
    except Exception as exc:
        crawl_service.mark_run_failed(db, crawl_run_id, str(exc))
        raise
    finally:
        db.close()


@celery_app.task(name="crawl.finalize_run", bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def crawl_finalize_run(self, crawl_run_id: str) -> dict:
    db = SessionLocal()
    try:
        run = crawl_service.get_run_or_404(db, crawl_run_id)
        run.status = "complete"
        if run.finished_at is None:
            run.finished_at = datetime.now(UTC)
        db.commit()
        return {"crawl_run_id": crawl_run_id, "status": run.status}
    except Exception as exc:
        crawl_service.mark_run_failed(db, crawl_run_id, str(exc))
        raise
    finally:
        db.close()

import json
from datetime import UTC, datetime

from app.db.session import SessionLocal
from app.models.crawl import CrawlPageResult
from app.models.task_execution import TaskExecution
from app.services import crawl_metrics, crawl_service
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


def _start_task_execution(db, tenant_id: str, task_name: str, payload: dict) -> TaskExecution:
    row = TaskExecution(
        tenant_id=tenant_id,
        task_name=task_name,
        status="running",
        payload_json=json.dumps(payload),
        result_json="{}",
    )
    db.add(row)
    db.flush()
    return row


def _finish_task_execution(db, row: TaskExecution, status: str, result: dict) -> None:
    row.status = status
    row.result_json = json.dumps(result)
    row.updated_at = datetime.now(UTC)
    db.commit()


@celery_app.task(name="crawl.schedule_campaign", bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def crawl_schedule_campaign(self, campaign_id: str, crawl_run_id: str, tenant_id: str) -> dict:
    db = SessionLocal()
    payload = {"campaign_id": campaign_id, "crawl_run_id": crawl_run_id, "tenant_id": tenant_id}
    execution = _start_task_execution(db, tenant_id, "crawl.schedule_campaign", payload)
    try:
        with crawl_metrics.stage_timer("crawl.schedule_campaign"):
            run = crawl_service.get_run_or_404(db, crawl_run_id)
            urls = crawl_service.build_batch_urls(run.seed_url, run.crawl_type)
            crawl_fetch_batch.delay(crawl_run_id=crawl_run_id, batch_urls=urls)
            result = {"campaign_id": campaign_id, "crawl_run_id": crawl_run_id, "tenant_id": tenant_id, "status": "queued"}
            _finish_task_execution(db, execution, "success", result)
            return result
    except Exception as exc:
        crawl_service.mark_run_failed(db, crawl_run_id, str(exc))
        _finish_task_execution(db, execution, "failed", {"error": str(exc)})
        raise
    finally:
        db.close()


@celery_app.task(name="crawl.fetch_batch", bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def crawl_fetch_batch(self, crawl_run_id: str, batch_urls: list[str]) -> dict:
    db = SessionLocal()
    run = crawl_service.get_run_or_404(db, crawl_run_id)
    execution = _start_task_execution(
        db,
        run.tenant_id,
        "crawl.fetch_batch",
        {"crawl_run_id": crawl_run_id, "batch_urls": batch_urls},
    )
    try:
        with crawl_metrics.stage_timer("crawl.fetch_batch"):
            result = crawl_service.execute_run(db, crawl_run_id=crawl_run_id, provided_urls=batch_urls)
            _finish_task_execution(db, execution, "success", result)
            return result
    except Exception as exc:
        crawl_service.mark_run_failed(db, crawl_run_id, str(exc))
        _finish_task_execution(db, execution, "failed", {"error": str(exc)})
        raise
    finally:
        db.close()


@celery_app.task(name="crawl.parse_page", bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def crawl_parse_page(self, crawl_run_id: str, url: str, html: str, status_code: int | None = 200) -> dict:
    db = SessionLocal()
    run = crawl_service.get_run_or_404(db, crawl_run_id)
    execution = _start_task_execution(
        db,
        run.tenant_id,
        "crawl.parse_page",
        {"crawl_run_id": crawl_run_id, "url": url, "status_code": status_code},
    )
    try:
        with crawl_metrics.stage_timer("crawl.parse_page"):
            result, _signals = crawl_service.record_page_result(db, run, url=url, status_code=status_code, html=html)
            db.flush()
            payload = {"crawl_run_id": crawl_run_id, "url": url, "page_result_id": result.id}
            _finish_task_execution(db, execution, "success", payload)
            return payload
    except Exception as exc:
        crawl_service.mark_run_failed(db, crawl_run_id, str(exc))
        _finish_task_execution(db, execution, "failed", {"error": str(exc)})
        raise
    finally:
        db.close()


@celery_app.task(name="crawl.extract_issues", bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def crawl_extract_issues(self, crawl_run_id: str, page_result_id: str) -> dict:
    db = SessionLocal()
    run = crawl_service.get_run_or_404(db, crawl_run_id)
    execution = _start_task_execution(
        db,
        run.tenant_id,
        "crawl.extract_issues",
        {"crawl_run_id": crawl_run_id, "page_result_id": page_result_id},
    )
    try:
        with crawl_metrics.stage_timer("crawl.extract_issues"):
            result = (
                db.query(CrawlPageResult)
                .filter(CrawlPageResult.id == page_result_id, CrawlPageResult.crawl_run_id == crawl_run_id)
                .first()
            )
            if result is None:
                payload = {"crawl_run_id": crawl_run_id, "page_result_id": page_result_id, "issues_found": 0}
                _finish_task_execution(db, execution, "success", payload)
                return payload
            issues = crawl_service.extract_issues_for_result(db, run, result)
            payload = {"crawl_run_id": crawl_run_id, "page_result_id": page_result_id, "issues_found": len(issues)}
            _finish_task_execution(db, execution, "success", payload)
            return payload
    except Exception as exc:
        crawl_service.mark_run_failed(db, crawl_run_id, str(exc))
        _finish_task_execution(db, execution, "failed", {"error": str(exc)})
        raise
    finally:
        db.close()


@celery_app.task(name="crawl.finalize_run", bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def crawl_finalize_run(self, crawl_run_id: str) -> dict:
    db = SessionLocal()
    run = crawl_service.get_run_or_404(db, crawl_run_id)
    execution = _start_task_execution(
        db,
        run.tenant_id,
        "crawl.finalize_run",
        {"crawl_run_id": crawl_run_id},
    )
    try:
        with crawl_metrics.stage_timer("crawl.finalize_run"):
            run.status = "complete"
            if run.finished_at is None:
                run.finished_at = datetime.now(UTC)
            payload = {"crawl_run_id": crawl_run_id, "status": run.status}
            _finish_task_execution(db, execution, "success", payload)
            return payload
    except Exception as exc:
        crawl_service.mark_run_failed(db, crawl_run_id, str(exc))
        _finish_task_execution(db, execution, "failed", {"error": str(exc)})
        raise
    finally:
        db.close()

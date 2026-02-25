import json
from datetime import UTC, datetime

import httpx
from celery import Task
from kombu.exceptions import KombuError
from app.db.session import SessionLocal
from app.models.campaign import Campaign
from app.models.crawl import CrawlPageResult
from app.models.task_execution import TaskExecution
from app.services import (
    authority_service,
    competitor_service,
    content_service,
    crawl_metrics,
    crawl_service,
    entity_service,
    fleet_service,
    intelligence_service,
    idempotency_service,
    local_service,
    observability_service,
    portfolio_usage_service,
    reference_library_service,
    rank_service,
    reporting_service,
)
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


@celery_app.task(name="governance.recover_stale_strategy_executions", bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 2})
def governance_recover_stale_strategy_executions(self, timeout_seconds: int = 900, batch_size: int = 100) -> dict:
    db = SessionLocal()
    execution = _start_task_execution(
        db,
        "system",
        "governance.recover_stale_strategy_executions",
        {"timeout_seconds": timeout_seconds, "batch_size": batch_size},
    )
    try:
        result = idempotency_service.recover_stale_running_executions(
            db,
            timeout_seconds=timeout_seconds,
            batch_size=batch_size,
        )
        _finish_task_execution(db, execution, "success", result)
        return result
    except Exception as exc:
        _finish_task_execution(db, execution, "failed", _task_failure_payload(self, exc))
        raise
    finally:
        db.close()


def _start_task_execution(db, tenant_id: str, task_name: str, payload: dict) -> TaskExecution:
    observability_service.record_task_started(payload)
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
    observability_service.record_task_finished(success=status == "success")
    row.status = status
    row.result_json = json.dumps(result, default=str)
    row.updated_at = datetime.now(UTC)
    db.commit()


def _is_retryable_error(exc: Exception) -> bool:
    return isinstance(exc, (httpx.HTTPError, TimeoutError, ConnectionError, OSError, KombuError))


def _reason_code(exc: Exception) -> str:
    name = exc.__class__.__name__.lower()
    if "timeout" in name:
        return "timeout"
    if "connect" in name or "connection" in name:
        return "connection_error"
    if "http" in name:
        return "upstream_http_error"
    if "kombu" in name:
        return "queue_broker_error"
    return "internal_error"


def _task_failure_payload(task: Task, exc: Exception) -> dict:
    current_retry = int(getattr(getattr(task, "request", None), "retries", 0) or 0)
    max_retries = getattr(task, "max_retries", None)
    dead_letter = bool(max_retries is not None and current_retry >= int(max_retries))
    return {
        "error": str(exc),
        "error_type": exc.__class__.__name__,
        "reason_code": _reason_code(exc),
        "retryable": _is_retryable_error(exc),
        "current_retry": current_retry,
        "max_retries": max_retries,
        "dead_letter": dead_letter,
    }


@celery_app.task(name="crawl.schedule_campaign", bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def crawl_schedule_campaign(self, campaign_id: str, crawl_run_id: str, tenant_id: str) -> dict:
    db = SessionLocal()
    payload = {"campaign_id": campaign_id, "crawl_run_id": crawl_run_id, "tenant_id": tenant_id}
    execution = _start_task_execution(db, tenant_id, "crawl.schedule_campaign", payload)
    try:
        with crawl_metrics.stage_timer("crawl.schedule_campaign"):
            run = crawl_service.get_run_or_404(db, crawl_run_id)
            seeded = crawl_service.seed_frontier_for_run(db, run)
            crawl_fetch_batch.delay(crawl_run_id=crawl_run_id)
            result = {
                "campaign_id": campaign_id,
                "crawl_run_id": crawl_run_id,
                "tenant_id": tenant_id,
                "status": "queued",
                "seeded_frontier_urls": seeded,
            }
            _finish_task_execution(db, execution, "success", result)
            return result
    except Exception as exc:
        crawl_service.mark_run_failed(db, crawl_run_id, str(exc))
        _finish_task_execution(db, execution, "failed", _task_failure_payload(self, exc))
        raise
    finally:
        db.close()


@celery_app.task(name="crawl.fetch_batch", bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def crawl_fetch_batch(self, crawl_run_id: str, batch_urls: list[str] | None = None, batch_size: int | None = None) -> dict:
    db = SessionLocal()
    run = crawl_service.get_run_or_404(db, crawl_run_id)
    execution = _start_task_execution(
        db,
        run.tenant_id,
        "crawl.fetch_batch",
        {"crawl_run_id": crawl_run_id, "batch_urls": batch_urls, "batch_size": batch_size},
    )
    try:
        with crawl_metrics.stage_timer("crawl.fetch_batch"):
            result = crawl_service.execute_run(
                db,
                crawl_run_id=crawl_run_id,
                provided_urls=batch_urls,
                batch_size=batch_size,
            )
            if batch_urls is None and result.get("status") == "running" and int(result.get("pending_urls", 0)) > 0:
                crawl_fetch_batch.delay(crawl_run_id=crawl_run_id, batch_size=batch_size)
            _finish_task_execution(db, execution, "success", result)
            return result
    except Exception as exc:
        crawl_service.mark_run_failed(db, crawl_run_id, str(exc))
        _finish_task_execution(db, execution, "failed", _task_failure_payload(self, exc))
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
        _finish_task_execution(db, execution, "failed", _task_failure_payload(self, exc))
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
        _finish_task_execution(db, execution, "failed", _task_failure_payload(self, exc))
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
        _finish_task_execution(db, execution, "failed", _task_failure_payload(self, exc))
        raise
    finally:
        db.close()


@celery_app.task(name="rank.schedule_window", bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def rank_schedule_window(self, campaign_id: str, tenant_id: str, location_code: str) -> dict:
    db = SessionLocal()
    execution = _start_task_execution(
        db,
        tenant_id,
        "rank.schedule_window",
        {"campaign_id": campaign_id, "location_code": location_code},
    )
    try:
        result = rank_service.run_snapshot_collection(
            db,
            tenant_id=tenant_id,
            campaign_id=campaign_id,
            location_code=location_code,
        )
        _finish_task_execution(db, execution, "success", result)
        return result
    except Exception as exc:
        _finish_task_execution(db, execution, "failed", _task_failure_payload(self, exc))
        raise
    finally:
        db.close()


@celery_app.task(name="rank.fetch_serp_batch")
def rank_fetch_serp_batch(campaign_id: str, tenant_id: str, location_code: str) -> dict:
    db = SessionLocal()
    execution = _start_task_execution(
        db,
        tenant_id,
        "rank.fetch_serp_batch",
        {"campaign_id": campaign_id, "location_code": location_code},
    )
    try:
        result = rank_service.run_snapshot_collection(
            db,
            tenant_id=tenant_id,
            campaign_id=campaign_id,
            location_code=location_code,
        )
        _finish_task_execution(db, execution, "success", result)
        return result
    finally:
        db.close()


@celery_app.task(name="rank.normalize_snapshot")
def rank_normalize_snapshot(snapshot_id: str) -> dict:
    db = SessionLocal()
    execution = _start_task_execution(
        db,
        "system",
        "rank.normalize_snapshot",
        {"snapshot_id": snapshot_id},
    )
    try:
        result = rank_service.normalize_snapshot(db, snapshot_id=snapshot_id)
        _finish_task_execution(db, execution, "success", result)
        return result
    finally:
        db.close()


@celery_app.task(name="rank.compute_deltas")
def rank_compute_deltas(campaign_id: str, tenant_id: str) -> dict:
    db = SessionLocal()
    execution = _start_task_execution(
        db,
        tenant_id,
        "rank.compute_deltas",
        {"campaign_id": campaign_id},
    )
    try:
        result = rank_service.recompute_deltas(db, tenant_id=tenant_id, campaign_id=campaign_id)
        _finish_task_execution(db, execution, "success", result)
        return result
    finally:
        db.close()


@celery_app.task(name="competitor.refresh_baseline")
def competitor_refresh_baseline(campaign_id: str, tenant_id: str) -> dict:
    db = SessionLocal()
    execution = _start_task_execution(
        db,
        tenant_id,
        "competitor.refresh_baseline",
        {"campaign_id": campaign_id},
    )
    try:
        result = competitor_service.collect_snapshot(db, tenant_id=tenant_id, campaign_id=campaign_id)
        _finish_task_execution(db, execution, "success", result)
        return result
    finally:
        db.close()


@celery_app.task(name="competitor.collect_snapshot", bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def competitor_collect_snapshot(self, campaign_id: str, tenant_id: str) -> dict:
    db = SessionLocal()
    execution = _start_task_execution(
        db,
        tenant_id,
        "competitor.collect_snapshot",
        {"campaign_id": campaign_id},
    )
    try:
        result = competitor_service.collect_snapshot(db, tenant_id=tenant_id, campaign_id=campaign_id)
        _finish_task_execution(db, execution, "success", result)
        return result
    except Exception as exc:
        _finish_task_execution(db, execution, "failed", {"error": str(exc)})
        raise
    finally:
        db.close()


@celery_app.task(name="competitor.compute_gap_scores")
def competitor_compute_gap_scores(campaign_id: str, tenant_id: str) -> dict:
    db = SessionLocal()
    try:
        gaps = competitor_service.compute_gaps(db, tenant_id=tenant_id, campaign_id=campaign_id)
        return {"campaign_id": campaign_id, "tenant_id": tenant_id, "gap_count": len(gaps)}
    finally:
        db.close()


@celery_app.task(name="content.generate_plan", bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def content_generate_plan(self, tenant_id: str, campaign_id: str, month_number: int) -> dict:
    db = SessionLocal()
    execution = _start_task_execution(
        db,
        tenant_id,
        "content.generate_plan",
        {"campaign_id": campaign_id, "month_number": month_number},
    )
    try:
        result = content_service.generate_plan(db, tenant_id=tenant_id, campaign_id=campaign_id, month_number=month_number)
        _finish_task_execution(db, execution, "success", result)
        return result
    except Exception as exc:
        _finish_task_execution(db, execution, "failed", {"error": str(exc)})
        raise
    finally:
        db.close()


@celery_app.task(name="content.run_qc_checks", bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def content_run_qc_checks(self, tenant_id: str, asset_id: str) -> dict:
    db = SessionLocal()
    execution = _start_task_execution(
        db,
        tenant_id,
        "content.run_qc_checks",
        {"asset_id": asset_id},
    )
    try:
        result = content_service.run_qc_checks(db, tenant_id=tenant_id, asset_id=asset_id)
        _finish_task_execution(db, execution, "success", result)
        return result
    except Exception as exc:
        _finish_task_execution(db, execution, "failed", {"error": str(exc)})
        raise
    finally:
        db.close()


@celery_app.task(name="content.refresh_internal_link_map", bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def content_refresh_internal_link_map(self, tenant_id: str, campaign_id: str) -> dict:
    db = SessionLocal()
    execution = _start_task_execution(
        db,
        tenant_id,
        "content.refresh_internal_link_map",
        {"campaign_id": campaign_id},
    )
    try:
        result = content_service.refresh_internal_link_map(db, tenant_id=tenant_id, campaign_id=campaign_id)
        _finish_task_execution(db, execution, "success", result)
        return result
    except Exception as exc:
        _finish_task_execution(db, execution, "failed", {"error": str(exc)})
        raise
    finally:
        db.close()


@celery_app.task(name="local.collect_profile_snapshot", bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def local_collect_profile_snapshot(self, tenant_id: str, campaign_id: str) -> dict:
    db = SessionLocal()
    execution = _start_task_execution(
        db,
        tenant_id,
        "local.collect_profile_snapshot",
        {"campaign_id": campaign_id},
    )
    try:
        profile = local_service.collect_profile_snapshot(db, tenant_id=tenant_id, campaign_id=campaign_id)
        result = {"campaign_id": campaign_id, "profile_id": profile.id, "map_pack_position": profile.map_pack_position}
        _finish_task_execution(db, execution, "success", result)
        return result
    except Exception as exc:
        _finish_task_execution(db, execution, "failed", {"error": str(exc)})
        raise
    finally:
        db.close()


@celery_app.task(name="local.compute_health_score", bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def local_compute_health_score(self, tenant_id: str, campaign_id: str) -> dict:
    db = SessionLocal()
    execution = _start_task_execution(
        db,
        tenant_id,
        "local.compute_health_score",
        {"campaign_id": campaign_id},
    )
    try:
        result = local_service.compute_health_score(db, tenant_id=tenant_id, campaign_id=campaign_id)
        _finish_task_execution(db, execution, "success", result)
        return result
    except Exception as exc:
        _finish_task_execution(db, execution, "failed", {"error": str(exc)})
        raise
    finally:
        db.close()


@celery_app.task(name="reviews.ingest", bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def reviews_ingest(self, tenant_id: str, campaign_id: str) -> dict:
    db = SessionLocal()
    execution = _start_task_execution(
        db,
        tenant_id,
        "reviews.ingest",
        {"campaign_id": campaign_id},
    )
    try:
        result = local_service.ingest_reviews(db, tenant_id=tenant_id, campaign_id=campaign_id)
        _finish_task_execution(db, execution, "success", result)
        return result
    except Exception as exc:
        _finish_task_execution(db, execution, "failed", {"error": str(exc)})
        raise
    finally:
        db.close()


@celery_app.task(name="reviews.compute_velocity", bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def reviews_compute_velocity(self, tenant_id: str, campaign_id: str) -> dict:
    db = SessionLocal()
    execution = _start_task_execution(
        db,
        tenant_id,
        "reviews.compute_velocity",
        {"campaign_id": campaign_id},
    )
    try:
        result = local_service.compute_review_velocity(db, tenant_id=tenant_id, campaign_id=campaign_id)
        _finish_task_execution(db, execution, "success", result)
        return result
    except Exception as exc:
        _finish_task_execution(db, execution, "failed", {"error": str(exc)})
        raise
    finally:
        db.close()


@celery_app.task(name="outreach.enrich_contacts", bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def outreach_enrich_contacts(self, tenant_id: str, campaign_id: str) -> dict:
    db = SessionLocal()
    execution = _start_task_execution(
        db,
        tenant_id,
        "outreach.enrich_contacts",
        {"campaign_id": campaign_id},
    )
    try:
        result = authority_service.enrich_outreach_contacts(db, tenant_id=tenant_id, campaign_id=campaign_id)
        _finish_task_execution(db, execution, "success", result)
        return result
    except Exception as exc:
        _finish_task_execution(db, execution, "failed", {"error": str(exc)})
        raise
    finally:
        db.close()


@celery_app.task(name="outreach.execute_sequence_step", bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def outreach_execute_sequence_step(self, tenant_id: str, outreach_campaign_id: str) -> dict:
    db = SessionLocal()
    execution = _start_task_execution(
        db,
        tenant_id,
        "outreach.execute_sequence_step",
        {"outreach_campaign_id": outreach_campaign_id},
    )
    try:
        result = authority_service.execute_outreach_sequence_step(
            db,
            tenant_id=tenant_id,
            outreach_campaign_id=outreach_campaign_id,
        )
        _finish_task_execution(db, execution, "success", result)
        return result
    except Exception as exc:
        _finish_task_execution(db, execution, "failed", {"error": str(exc)})
        raise
    finally:
        db.close()


@celery_app.task(name="authority.sync_backlinks", bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def authority_sync_backlinks(self, tenant_id: str, campaign_id: str) -> dict:
    db = SessionLocal()
    execution = _start_task_execution(
        db,
        tenant_id,
        "authority.sync_backlinks",
        {"campaign_id": campaign_id},
    )
    try:
        result = authority_service.sync_backlinks(db, tenant_id=tenant_id, campaign_id=campaign_id)
        _finish_task_execution(db, execution, "success", result)
        return result
    except Exception as exc:
        _finish_task_execution(db, execution, "failed", {"error": str(exc)})
        raise
    finally:
        db.close()


@celery_app.task(name="citation.submit_batch", bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def citation_submit_batch(self, tenant_id: str, campaign_id: str) -> dict:
    db = SessionLocal()
    execution = _start_task_execution(
        db,
        tenant_id,
        "citation.submit_batch",
        {"campaign_id": campaign_id},
    )
    try:
        result = authority_service.submit_citation_batch(db, tenant_id=tenant_id, campaign_id=campaign_id)
        _finish_task_execution(db, execution, "success", result)
        return result
    except Exception as exc:
        _finish_task_execution(db, execution, "failed", {"error": str(exc)})
        raise
    finally:
        db.close()


@celery_app.task(name="citation.refresh_status", bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def citation_refresh_status(self, tenant_id: str, campaign_id: str) -> dict:
    db = SessionLocal()
    execution = _start_task_execution(
        db,
        tenant_id,
        "citation.refresh_status",
        {"campaign_id": campaign_id},
    )
    try:
        rows = authority_service.refresh_citation_status(db, tenant_id=tenant_id, campaign_id=campaign_id)
        result = {"campaign_id": campaign_id, "citations_refreshed": len(rows)}
        _finish_task_execution(db, execution, "success", result)
        return result
    except Exception as exc:
        _finish_task_execution(db, execution, "failed", {"error": str(exc)})
        raise
    finally:
        db.close()


@celery_app.task(name="intelligence.compute_score", bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def intelligence_compute_score(self, tenant_id: str, campaign_id: str) -> dict:
    db = SessionLocal()
    execution = _start_task_execution(
        db,
        tenant_id,
        "intelligence.compute_score",
        {"campaign_id": campaign_id},
    )
    try:
        score = intelligence_service.compute_score(db, tenant_id=tenant_id, campaign_id=campaign_id)
        result = {"campaign_id": campaign_id, "score_value": score.score_value}
        _finish_task_execution(db, execution, "success", result)
        return result
    except Exception as exc:
        _finish_task_execution(db, execution, "failed", {"error": str(exc)})
        raise
    finally:
        db.close()


@celery_app.task(name="intelligence.detect_anomalies", bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def intelligence_detect_anomalies(self, tenant_id: str, campaign_id: str) -> dict:
    db = SessionLocal()
    execution = _start_task_execution(
        db,
        tenant_id,
        "intelligence.detect_anomalies",
        {"campaign_id": campaign_id},
    )
    try:
        result = intelligence_service.detect_anomalies(db, tenant_id=tenant_id, campaign_id=campaign_id)
        _finish_task_execution(db, execution, "success", result)
        return result
    except Exception as exc:
        _finish_task_execution(db, execution, "failed", {"error": str(exc)})
        raise
    finally:
        db.close()


@celery_app.task(name="campaigns.evaluate_monthly_rules", bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def campaigns_evaluate_monthly_rules(self, tenant_id: str, campaign_id: str, month_number: int) -> dict:
    db = SessionLocal()
    execution = _start_task_execution(
        db,
        tenant_id,
        "campaigns.evaluate_monthly_rules",
        {"campaign_id": campaign_id, "month_number": month_number},
    )
    try:
        result = intelligence_service.evaluate_monthly_rules(db, tenant_id=tenant_id, campaign_id=campaign_id, month_number=month_number)
        _finish_task_execution(db, execution, "success", result)
        return result
    except Exception as exc:
        _finish_task_execution(db, execution, "failed", {"error": str(exc)})
        raise
    finally:
        db.close()


@celery_app.task(name="campaigns.schedule_monthly_actions", bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def campaigns_schedule_monthly_actions(self, tenant_id: str, campaign_id: str, month_number: int) -> dict:
    db = SessionLocal()
    execution = _start_task_execution(
        db,
        tenant_id,
        "campaigns.schedule_monthly_actions",
        {"campaign_id": campaign_id, "month_number": month_number},
    )
    try:
        result = intelligence_service.schedule_monthly_actions(db, tenant_id=tenant_id, campaign_id=campaign_id, month_number=month_number)
        _finish_task_execution(db, execution, "success", result)
        return result
    except Exception as exc:
        _finish_task_execution(db, execution, "failed", {"error": str(exc)})
        raise
    finally:
        db.close()


@celery_app.task(name="reporting.freeze_window")
def reporting_freeze_window(tenant_id: str, campaign_id: str, month_number: int) -> dict:
    db = SessionLocal()
    execution = _start_task_execution(
        db,
        tenant_id,
        "reporting.freeze_window",
        {"campaign_id": campaign_id, "month_number": month_number},
    )
    try:
        report = reporting_service.generate_report(db, tenant_id=tenant_id, campaign_id=campaign_id, month_number=month_number)
        result = {"tenant_id": tenant_id, "campaign_id": campaign_id, "month_number": month_number, "frozen": True, "report_id": report.id}
        _finish_task_execution(db, execution, "success", result)
        return result
    finally:
        db.close()


@celery_app.task(name="reporting.aggregate_kpis", bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def reporting_aggregate_kpis(self, tenant_id: str, campaign_id: str, month_number: int) -> dict:
    db = SessionLocal()
    execution = _start_task_execution(
        db,
        tenant_id,
        "reporting.aggregate_kpis",
        {"campaign_id": campaign_id, "month_number": month_number},
    )
    try:
        result = reporting_service.aggregate_kpis(db, tenant_id=tenant_id, campaign_id=campaign_id, month_number=month_number)
        _finish_task_execution(db, execution, "success", result)
        return result
    except Exception as exc:
        _finish_task_execution(db, execution, "failed", {"error": str(exc)})
        raise
    finally:
        db.close()


@celery_app.task(name="reporting.render_html", bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def reporting_render_html(self, tenant_id: str, report_id: str) -> dict:
    db = SessionLocal()
    execution = _start_task_execution(
        db,
        tenant_id,
        "reporting.render_html",
        {"report_id": report_id},
    )
    try:
        report = reporting_service.get_report(db, tenant_id=tenant_id, report_id=report_id)
        kpis = json.loads(report.summary_json or "{}")
        html = reporting_service.render_html(kpis, campaign_name="Campaign")
        result = {"report_id": report_id, "html_length": len(html)}
        _finish_task_execution(db, execution, "success", result)
        return result
    except Exception as exc:
        _finish_task_execution(db, execution, "failed", {"error": str(exc)})
        raise
    finally:
        db.close()


@celery_app.task(name="reporting.render_pdf", bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def reporting_render_pdf(self, tenant_id: str, report_id: str) -> dict:
    db = SessionLocal()
    execution = _start_task_execution(
        db,
        tenant_id,
        "reporting.render_pdf",
        {"report_id": report_id},
    )
    try:
        report = reporting_service.get_report(db, tenant_id=tenant_id, report_id=report_id)
        kpis = json.loads(report.summary_json or "{}")
        campaign = db.get(Campaign, report.campaign_id) if report.campaign_id else None
        campaign_name = campaign.name if campaign is not None else "Campaign"
        path = reporting_service.render_pdf_report(kpis, report_id, campaign_name=campaign_name)
        result = {"report_id": report_id, "storage_path": path}
        _finish_task_execution(db, execution, "success", result)
        return result
    except Exception as exc:
        _finish_task_execution(db, execution, "failed", {"error": str(exc)})
        raise
    finally:
        db.close()


@celery_app.task(name="reporting.send_email", bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def reporting_send_email(self, tenant_id: str, report_id: str, recipient: str) -> dict:
    db = SessionLocal()
    execution = _start_task_execution(
        db,
        tenant_id,
        "reporting.send_email",
        {"report_id": report_id, "recipient": recipient},
    )
    try:
        result = reporting_service.deliver_report(db, tenant_id=tenant_id, report_id=report_id, recipient=recipient)
        _finish_task_execution(db, execution, "success", result)
        return result
    except Exception as exc:
        _finish_task_execution(db, execution, "failed", _task_failure_payload(self, exc))
        raise
    finally:
        db.close()


@celery_app.task(name="reporting.process_schedule", bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 2})
def reporting_process_schedule(self, tenant_id: str, campaign_id: str) -> dict:
    db = SessionLocal()
    execution = _start_task_execution(
        db,
        tenant_id,
        "reporting.process_schedule",
        {"campaign_id": campaign_id},
    )
    try:
        result = reporting_service.run_due_report_schedule(db, tenant_id=tenant_id, campaign_id=campaign_id)
        _finish_task_execution(db, execution, "success", result)
        return result
    except Exception as exc:
        retry_state = reporting_service.mark_schedule_attempt_failure(db, tenant_id=tenant_id, campaign_id=campaign_id, error_message=str(exc))
        _finish_task_execution(db, execution, "failed", retry_state)
        if retry_state.get("should_retry"):
            raise
        return retry_state
    finally:
        db.close()


@celery_app.task(name="portfolio_usage.rollup_incremental", bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def portfolio_usage_rollup_incremental(self, through_date: str | None = None) -> dict:
    db = SessionLocal()
    execution = _start_task_execution(
        db,
        "system",
        "portfolio_usage.rollup_incremental",
        {"through_date": through_date},
    )
    try:
        result = portfolio_usage_service.rollup_portfolio_usage_incremental(db=db, through_date=through_date)
        _finish_task_execution(db, execution, "success", result)
        return result
    except Exception as exc:
        _finish_task_execution(db, execution, "failed", _task_failure_payload(self, exc))
        raise
    finally:
        db.close()


@celery_app.task(name="reference_library.validate_artifact", bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def reference_library_validate_artifact(
    self,
    tenant_id: str,
    actor_user_id: str,
    version: str,
    artifacts: dict | None = None,
    strict_mode: bool = True,
) -> dict:
    db = SessionLocal()
    execution = _start_task_execution(
        db,
        tenant_id,
        "reference_library.validate_artifact",
        {"version": version, "strict_mode": strict_mode},
    )
    try:
        result = reference_library_service.validate_version(
            db,
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            version=version,
            artifacts=artifacts,
            strict_mode=strict_mode,
        )
        _finish_task_execution(db, execution, "success", result)
        return result
    except Exception as exc:
        _finish_task_execution(db, execution, "failed", {"error": str(exc)})
        raise
    finally:
        db.close()


@celery_app.task(name="reference_library.activate_version", bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def reference_library_activate_version(self, tenant_id: str, actor_user_id: str, version: str, reason: str | None = None) -> dict:
    db = SessionLocal()
    execution = _start_task_execution(
        db,
        tenant_id,
        "reference_library.activate_version",
        {"version": version, "reason": reason or ""},
    )
    try:
        result = reference_library_service.activate_version(
            db,
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            version=version,
            reason=reason,
        )
        _finish_task_execution(db, execution, "success", result)
        return result
    except Exception as exc:
        _finish_task_execution(db, execution, "failed", {"error": str(exc)})
        raise
    finally:
        db.close()


@celery_app.task(name="reference_library.reload_cache")
def reference_library_reload_cache(tenant_id: str, version: str) -> dict:
    return {"tenant_id": tenant_id, "version": version, "cache_reloaded": True}


@celery_app.task(name="reference_library.rollback_version", bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def reference_library_rollback_version(self, tenant_id: str, actor_user_id: str, version: str) -> dict:
    db = SessionLocal()
    execution = _start_task_execution(
        db,
        tenant_id,
        "reference_library.rollback_version",
        {"version": version},
    )
    try:
        result = reference_library_service.activate_version(
            db,
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            version=version,
            reason="rollback",
        )
        payload = {"rolled_back_to": result["version"], "status": result["status"], "activation_id": result["activation_id"]}
        _finish_task_execution(db, execution, "success", payload)
        return payload
    except Exception as exc:
        _finish_task_execution(db, execution, "failed", {"error": str(exc)})
        raise
    finally:
        db.close()


@celery_app.task(name="entity.analyze_campaign", bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def entity_analyze_campaign(self, tenant_id: str, campaign_id: str) -> dict:
    db = SessionLocal()
    execution = _start_task_execution(
        db,
        tenant_id,
        "entity.analyze_campaign",
        {"campaign_id": campaign_id},
    )
    try:
        result = entity_service.run_entity_analysis(db, tenant_id=tenant_id, campaign_id=campaign_id)
        _finish_task_execution(db, execution, "success", result)
        return result
    except Exception as exc:
        _finish_task_execution(db, execution, "failed", _task_failure_payload(self, exc))
        raise
    finally:
        db.close()

@celery_app.task(name="fleet.process_fleet_job_item_task")
def process_fleet_job_item_task(fleet_job_item_id: str):
    return fleet_service.process_fleet_job_item_with_new_session(fleet_job_item_id)
    

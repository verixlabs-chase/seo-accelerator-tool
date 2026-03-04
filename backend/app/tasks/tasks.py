import json
import logging
from datetime import UTC, datetime, timedelta

import httpx
from celery import Task
from kombu.exceptions import KombuError
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.domain import entitlement_codes
from app.models.campaign import Campaign
from app.models.organization import Organization
from app.models.crawl import CrawlPageResult
from app.models.rank import CampaignKeyword
from app.models.task_execution import TaskExecution
from app.services.entitlement_service import EntitlementNotFoundError, can_consume
from app.services import (
    analytics_service,
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
    traffic_fact_service,
)
from app.tasks.celery_app import celery_app

logger = logging.getLogger("lsos.traffic.facts")


@celery_app.task(name="ops.healthcheck.snapshot")
def ops_healthcheck_snapshot() -> dict:
    return {"timestamp": datetime.now(UTC).isoformat(), "status": "ok"}


@celery_app.task(name="analytics.rollup_daily", bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 2})
def analytics_rollup_daily(self, metric_date: str | None = None, tenant_id: str = "system") -> dict:
    db = SessionLocal()
    execution = _start_task_execution(db, tenant_id, "analytics.rollup_daily", {"metric_date": metric_date})
    try:
        resolved_metric_date = metric_date or (datetime.now(UTC).date() - timedelta(days=1)).isoformat()
        result = analytics_service.rollup_campaign_daily_metrics_for_date(db=db, metric_date=resolved_metric_date)
        payload = {
            "metric_date": result.metric_date.isoformat(),
            "processed_campaigns": result.processed_campaigns,
            "inserted_rows": result.inserted_rows,
            "updated_rows": result.updated_rows,
            "skipped_rows": result.skipped_rows,
        }
        _finish_task_execution(db, execution, "success", payload)
        return payload
    except Exception as exc:
        db.rollback()
        _finish_task_execution(db, execution, "failed", _task_failure_payload(self, exc))
        raise
    finally:
        db.close()


@celery_app.task(name="traffic.sync_search_console_daily_metrics_for_campaign", bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 2})
def sync_search_console_daily_metrics_for_campaign(
    self,
    campaign_id: str,
    start_date: str,
    end_date: str,
    tenant_id: str | None = None,
) -> dict:
    db = SessionLocal()
    campaign = db.get(Campaign, campaign_id)
    execution_tenant = tenant_id or (campaign.tenant_id if campaign is not None else "system")
    payload = {"campaign_id": campaign_id, "start_date": start_date, "end_date": end_date}
    execution = _start_task_execution(db, execution_tenant, "traffic.sync_search_console_daily_metrics_for_campaign", payload)
    started_at = datetime.now(UTC)
    try:
        if campaign is None:
            raise ValueError("Campaign not found")
        result = traffic_fact_service.sync_search_console_daily_metrics_for_campaign(
            db=db,
            campaign=campaign,
            start_date=start_date,
            end_date=end_date,
        )
        response = _traffic_fact_sync_payload(result)
        if response.get("reason_code") == "ORG_INACTIVE":
            _finish_task_execution(db, execution, "failed", response)
            return response
        _finish_task_execution(db, execution, "success", response)
        _log_traffic_fact_sync_completed(result=result, duration_ms=_duration_ms(started_at))
        return response
    except Exception as exc:
        db.rollback()
        duration_ms = _duration_ms(started_at)
        _log_traffic_fact_sync_failed(
            organization_id=str(getattr(campaign, "organization_id", "") or ""),
            campaign_id=campaign_id,
            start_date=start_date,
            end_date=end_date,
            duration_ms=duration_ms,
            error=str(exc),
        )
        _finish_task_execution(db, execution, "failed", _task_failure_payload(self, exc))
        raise
    finally:
        db.close()


@celery_app.task(name="traffic.sync_analytics_daily_metrics_for_campaign", bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 2})
def sync_analytics_daily_metrics_for_campaign(
    self,
    campaign_id: str,
    start_date: str,
    end_date: str,
    tenant_id: str | None = None,
) -> dict:
    db = SessionLocal()
    campaign = db.get(Campaign, campaign_id)
    execution_tenant = tenant_id or (campaign.tenant_id if campaign is not None else "system")
    payload = {"campaign_id": campaign_id, "start_date": start_date, "end_date": end_date}
    execution = _start_task_execution(db, execution_tenant, "traffic.sync_analytics_daily_metrics_for_campaign", payload)
    started_at = datetime.now(UTC)
    try:
        if campaign is None:
            raise ValueError("Campaign not found")
        result = traffic_fact_service.sync_analytics_daily_metrics_for_campaign(
            db=db,
            campaign=campaign,
            start_date=start_date,
            end_date=end_date,
        )
        response = _traffic_fact_sync_payload(result)
        if response.get("reason_code") == "ORG_INACTIVE":
            _finish_task_execution(db, execution, "failed", response)
            return response
        _finish_task_execution(db, execution, "success", response)
        _log_traffic_fact_sync_completed(result=result, duration_ms=_duration_ms(started_at))
        return response
    except Exception as exc:
        db.rollback()
        duration_ms = _duration_ms(started_at)
        _log_traffic_fact_sync_failed(
            organization_id=str(getattr(campaign, "organization_id", "") or ""),
            campaign_id=campaign_id,
            start_date=start_date,
            end_date=end_date,
            duration_ms=duration_ms,
            error=str(exc),
        )
        _finish_task_execution(db, execution, "failed", _task_failure_payload(self, exc))
        raise
    finally:
        db.close()


@celery_app.task(name="traffic.nightly_sync_traffic_facts", bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 1})
def nightly_sync_traffic_facts(self, lookback_days: int | None = None, tenant_id: str = "system") -> dict:
    db = SessionLocal()
    settings = get_settings()
    resolved_lookback_days = max(1, int(lookback_days or settings.traffic_fact_sync_lookback_days))
    end_date = datetime.now(UTC).date() - timedelta(days=1)
    start_date = end_date - timedelta(days=resolved_lookback_days - 1)
    payload = {
        "lookback_days": resolved_lookback_days,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
    }
    execution = _start_task_execution(db, tenant_id, "traffic.nightly_sync_traffic_facts", payload)
    processed_campaigns = 0
    failed_campaigns = 0
    search_synced_days = 0
    analytics_synced_days = 0
    try:
        campaigns = (
            db.query(Campaign)
            .filter(
                Campaign.setup_state == "Active",
                Campaign.organization_id.isnot(None),
            )
            .order_by(Campaign.created_at.asc(), Campaign.id.asc())
            .all()
        )
        campaign_refs = [(campaign.id, campaign.tenant_id) for campaign in campaigns]

        for campaign_id, campaign_tenant_id in campaign_refs:
            processed_campaigns += 1
            try:
                search_payload = sync_search_console_daily_metrics_for_campaign.run(
                    campaign_id=campaign_id,
                    start_date=start_date.isoformat(),
                    end_date=end_date.isoformat(),
                    tenant_id=campaign_tenant_id,
                )
                analytics_payload = sync_analytics_daily_metrics_for_campaign.run(
                    campaign_id=campaign_id,
                    start_date=start_date.isoformat(),
                    end_date=end_date.isoformat(),
                    tenant_id=campaign_tenant_id,
                )
                if search_payload.get("reason_code") == "ORG_INACTIVE" or analytics_payload.get("reason_code") == "ORG_INACTIVE":
                    failed_campaigns += 1
                    continue
                search_synced_days += int(search_payload.get("requested_days", 0))
                analytics_synced_days += int(analytics_payload.get("requested_days", 0))
            except Exception:
                failed_campaigns += 1
                continue

        analytics_rollup = analytics_service.rollup_campaign_daily_metrics_for_range(
            db=db,
            date_from=start_date,
            date_to=end_date,
        )
        response = {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "lookback_days": resolved_lookback_days,
            "processed_campaigns": processed_campaigns,
            "failed_campaigns": failed_campaigns,
            "search_synced_days": search_synced_days,
            "analytics_synced_days": analytics_synced_days,
            "rollup_days_processed": analytics_rollup.days_processed,
        }
        _finish_task_execution(db, execution, "success", response)
        return response
    except Exception as exc:
        db.rollback()
        _finish_task_execution(db, execution, "failed", _task_failure_payload(self, exc))
        raise
    finally:
        db.close()


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


def _traffic_fact_sync_payload(result: traffic_fact_service.TrafficFactSyncResult) -> dict:
    return {
        "organization_id": result.organization_id,
        "campaign_id": result.campaign_id,
        "start_date": result.start_date.isoformat(),
        "end_date": result.end_date.isoformat(),
        "requested_days": result.requested_days,
        "provider_calls": result.provider_calls,
        "inserted_rows": result.inserted_rows,
        "updated_rows": result.updated_rows,
        "skipped_rows": result.skipped_rows,
        "replay_skipped": result.replay_skipped,
        "status": result.status,
        "reason_code": result.reason_code,
    }


def _duration_ms(started_at: datetime) -> int:
    return max(0, int((datetime.now(UTC) - started_at).total_seconds() * 1000))


def _log_traffic_fact_sync_completed(*, result: traffic_fact_service.TrafficFactSyncResult, duration_ms: int) -> None:
    logger.info(
        json.dumps(
            {
                "event": "traffic_fact_sync_completed",
                "organization_id": result.organization_id,
                "campaign_id": result.campaign_id,
                "start_date": result.start_date.isoformat(),
                "end_date": result.end_date.isoformat(),
                "duration_ms": duration_ms,
                "requested_days": result.requested_days,
                "provider_calls": result.provider_calls,
                "replay_skipped": result.replay_skipped,
            },
            sort_keys=True,
        )
    )


def _log_traffic_fact_sync_failed(
    *,
    organization_id: str,
    campaign_id: str,
    start_date: str,
    end_date: str,
    duration_ms: int,
    error: str,
) -> None:
    logger.error(
        json.dumps(
            {
                "event": "traffic_fact_sync_failed",
                "organization_id": organization_id,
                "campaign_id": campaign_id,
                "start_date": start_date,
                "end_date": end_date,
                "duration_ms": duration_ms,
                "error": error,
            },
            sort_keys=True,
        )
    )


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



def _precheck_crawl_page_entitlement(db, *, crawl_run_id: str, provided_urls: list[str] | None = None) -> dict | None:
    run = crawl_service.get_run_or_404(db, crawl_run_id)
    if run.started_at is not None:
        return None

    campaign = db.get(Campaign, run.campaign_id)
    if campaign is None or campaign.organization_id is None:
        raise EntitlementNotFoundError(
            f"Campaign missing organization_id for crawl entitlement enforcement: {run.campaign_id}"
        )
    organization = db.get(Organization, campaign.organization_id)
    if organization is None:
        raise ValueError(f"Organization not found for crawl run: {crawl_run_id}")
    if organization.status.strip().lower() != "active":
        return {
            "crawl_run_id": crawl_run_id,
            "campaign_id": run.campaign_id,
            "status": "failed",
            "reason_code": "ORG_INACTIVE",
        }

    planned_page_count = crawl_service.get_planned_page_count(
        db,
        crawl_run_id=crawl_run_id,
        provided_urls=provided_urls,
    )
    if planned_page_count <= 0:
        return None

    allowed = can_consume(
        db,
        str(campaign.organization_id),
        entitlement_codes.LIMIT_CRAWL_PAGES_MONTHLY,
        amount=planned_page_count,
    )
    if allowed:
        return None

    return {
        "crawl_run_id": crawl_run_id,
        "campaign_id": run.campaign_id,
        "status": "failed",
        "reason_code": "ENTITLEMENT_EXCEEDED",
        "planned_pages": planned_page_count,
    }


@celery_app.task(name="crawl.schedule_campaign", bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def crawl_schedule_campaign(self, campaign_id: str, crawl_run_id: str, tenant_id: str) -> dict:
    db = SessionLocal()
    payload = {"campaign_id": campaign_id, "crawl_run_id": crawl_run_id, "tenant_id": tenant_id}
    execution = _start_task_execution(db, tenant_id, "crawl.schedule_campaign", payload)
    try:
        with crawl_metrics.stage_timer("crawl.schedule_campaign"):
            precheck_failure = _precheck_crawl_page_entitlement(db, crawl_run_id=crawl_run_id)
            if precheck_failure is not None:
                crawl_service.mark_run_failed(db, crawl_run_id, "ENTITLEMENT_EXCEEDED")
                _finish_task_execution(db, execution, "failed", precheck_failure)
                return precheck_failure

            run = crawl_service.get_run_or_404(db, crawl_run_id)
            seeded = crawl_service.seed_frontier_for_run(db, run)
            # Commit seeded frontier rows before dispatching follow-up work.
            # In eager task mode, .delay() may execute synchronously.
            db.commit()
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
    except EntitlementNotFoundError as exc:
        crawl_service.mark_run_failed(db, crawl_run_id, str(exc))
        failure = {
            "crawl_run_id": crawl_run_id,
            "campaign_id": campaign_id,
            "status": "failed",
            "reason_code": "ENTITLEMENT_NOT_FOUND",
            "error": str(exc),
        }
        _finish_task_execution(db, execution, "failed", failure)
        return failure
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
            precheck_failure = _precheck_crawl_page_entitlement(
                db,
                crawl_run_id=crawl_run_id,
                provided_urls=batch_urls,
            )
            if precheck_failure is not None:
                crawl_service.mark_run_failed(db, crawl_run_id, "ENTITLEMENT_EXCEEDED")
                _finish_task_execution(db, execution, "failed", precheck_failure)
                return precheck_failure

            result = crawl_service.execute_run(
                db,
                crawl_run_id=crawl_run_id,
                provided_urls=batch_urls,
                batch_size=batch_size,
            )
            if result.get("reason_code") in {"ENTITLEMENT_EXCEEDED", "ORG_INACTIVE"}:
                crawl_service.mark_run_failed(db, crawl_run_id, "ENTITLEMENT_EXCEEDED")
                _finish_task_execution(db, execution, "failed", result)
                return result
            if batch_urls is None and result.get("status") == "running" and int(result.get("pending_urls", 0)) > 0:
                crawl_fetch_batch.delay(crawl_run_id=crawl_run_id, batch_size=batch_size)
            _finish_task_execution(db, execution, "success", result)
            return result
    except EntitlementNotFoundError as exc:
        crawl_service.mark_run_failed(db, crawl_run_id, str(exc))
        failure = {
            "crawl_run_id": crawl_run_id,
            "status": "failed",
            "reason_code": "ENTITLEMENT_NOT_FOUND",
            "error": str(exc),
        }
        _finish_task_execution(db, execution, "failed", failure)
        return failure
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



def _precheck_rank_snapshot_entitlement(db, *, campaign_id: str, tenant_id: str, location_code: str) -> dict | None:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None:
        return None

    keyword_count = (
        db.query(CampaignKeyword)
        .filter(
            CampaignKeyword.tenant_id == tenant_id,
            CampaignKeyword.campaign_id == campaign_id,
            CampaignKeyword.location_code == location_code,
        )
        .count()
    )
    if keyword_count <= 0:
        return None
    if campaign.organization_id is None:
        raise EntitlementNotFoundError(
            f"Campaign missing organization_id for rank snapshot enforcement: {campaign_id}"
        )

    allowed = can_consume(
        db,
        str(campaign.organization_id),
        entitlement_codes.LIMIT_RANK_KEYWORD_SNAPSHOTS_MONTHLY,
        amount=keyword_count,
    )
    if allowed:
        return None

    return {
        "campaign_id": campaign_id,
        "location_code": location_code,
        "status": "failed",
        "reason_code": "ENTITLEMENT_EXCEEDED",
        "snapshots_created": 0,
    }


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
        precheck_failure = _precheck_rank_snapshot_entitlement(
            db,
            campaign_id=campaign_id,
            tenant_id=tenant_id,
            location_code=location_code,
        )
        if precheck_failure is not None:
            _finish_task_execution(db, execution, "failed", precheck_failure)
            return precheck_failure

        result = rank_service.run_snapshot_collection(
            db,
            tenant_id=tenant_id,
            campaign_id=campaign_id,
            location_code=location_code,
        )
        if result.get("reason_code") in {"ENTITLEMENT_EXCEEDED", "ORG_INACTIVE"}:
            failure = {
                "campaign_id": campaign_id,
                "location_code": location_code,
                "status": "failed",
                "reason_code": result.get("reason_code"),
                "snapshots_created": int(result.get("snapshots_created", 0)),
            }
            _finish_task_execution(db, execution, "failed", failure)
            return failure
        _finish_task_execution(db, execution, "success", result)
        return result
    except EntitlementNotFoundError as exc:
        failure = {
            "campaign_id": campaign_id,
            "location_code": location_code,
            "status": "failed",
            "reason_code": "ENTITLEMENT_NOT_FOUND",
            "error": str(exc),
        }
        _finish_task_execution(db, execution, "failed", failure)
        return failure
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
        precheck_failure = _precheck_rank_snapshot_entitlement(
            db,
            campaign_id=campaign_id,
            tenant_id=tenant_id,
            location_code=location_code,
        )
        if precheck_failure is not None:
            _finish_task_execution(db, execution, "failed", precheck_failure)
            return precheck_failure

        result = rank_service.run_snapshot_collection(
            db,
            tenant_id=tenant_id,
            campaign_id=campaign_id,
            location_code=location_code,
        )
        if result.get("reason_code") in {"ENTITLEMENT_EXCEEDED", "ORG_INACTIVE"}:
            failure = {
                "campaign_id": campaign_id,
                "location_code": location_code,
                "status": "failed",
                "reason_code": result.get("reason_code"),
                "snapshots_created": int(result.get("snapshots_created", 0)),
            }
            _finish_task_execution(db, execution, "failed", failure)
            return failure
        _finish_task_execution(db, execution, "success", result)
        return result
    except EntitlementNotFoundError as exc:
        failure = {
            "campaign_id": campaign_id,
            "location_code": location_code,
            "status": "failed",
            "reason_code": "ENTITLEMENT_NOT_FOUND",
            "error": str(exc),
        }
        _finish_task_execution(db, execution, "failed", failure)
        return failure
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
    

@celery_app.task(name="strategy.run_automation_for_all_campaigns", bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 2})
def run_strategy_automation_for_all_campaigns(self, evaluation_date_iso: str | None = None) -> dict:
    from app.services.strategy_engine.automation_engine import evaluate_campaign_for_automation

    db = SessionLocal()
    execution = _start_task_execution(
        db,
        "system",
        "strategy.run_automation_for_all_campaigns",
        {"evaluation_date_iso": evaluation_date_iso or ""},
    )
    try:
        evaluation_date = datetime.now(UTC)
        if evaluation_date_iso:
            parsed = datetime.fromisoformat(evaluation_date_iso.replace("Z", "+00:00"))
            evaluation_date = parsed.astimezone(UTC)

        campaigns = db.query(Campaign).order_by(Campaign.created_at.asc(), Campaign.id.asc()).all()
        results: list[dict] = []
        failures: list[dict[str, str]] = []

        for campaign in campaigns:
            try:
                results.append(
                    evaluate_campaign_for_automation(
                        campaign_id=campaign.id,
                        db=db,
                        evaluation_date=evaluation_date,
                    )
                )
            except Exception as exc:  # pragma: no cover - defensive non-blocking task behavior
                db.rollback()
                failures.append({"campaign_id": campaign.id, "error": str(exc)})

        summary = {
            "evaluation_date": evaluation_date.isoformat(),
            "campaigns_scanned": len(campaigns),
            "campaigns_evaluated": len(results),
            "campaign_failures": len(failures),
            "failures": failures,
            "result_status_counts": {
                "evaluated": sum(1 for item in results if item.get("status") == "evaluated"),
                "already_evaluated": sum(1 for item in results if item.get("status") == "already_evaluated"),
                "frozen": sum(1 for item in results if item.get("status") == "frozen"),
                "campaign_not_found": sum(1 for item in results if item.get("status") == "campaign_not_found"),
            },
        }
        _finish_task_execution(db, execution, "success", summary)
        return summary
    except Exception as exc:
        _finish_task_execution(db, execution, "failed", _task_failure_payload(self, exc))
        raise
    finally:
        db.close()










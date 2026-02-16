import json
from datetime import UTC, datetime

from app.db.session import SessionLocal
from app.models.crawl import CrawlPageResult
from app.models.task_execution import TaskExecution
from app.services import authority_service, competitor_service, content_service, crawl_metrics, crawl_service, local_service, rank_service
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
        _finish_task_execution(db, execution, "failed", {"error": str(exc)})
        raise
    finally:
        db.close()


@celery_app.task(name="rank.fetch_serp_batch")
def rank_fetch_serp_batch(campaign_id: str, tenant_id: str, location_code: str) -> dict:
    return {"campaign_id": campaign_id, "tenant_id": tenant_id, "location_code": location_code, "fetched": True}


@celery_app.task(name="rank.normalize_snapshot")
def rank_normalize_snapshot(snapshot_id: str) -> dict:
    return {"snapshot_id": snapshot_id, "normalized": True}


@celery_app.task(name="rank.compute_deltas")
def rank_compute_deltas(campaign_id: str, tenant_id: str) -> dict:
    return {"campaign_id": campaign_id, "tenant_id": tenant_id, "computed": True}


@celery_app.task(name="competitor.refresh_baseline")
def competitor_refresh_baseline(campaign_id: str, tenant_id: str) -> dict:
    return {"campaign_id": campaign_id, "tenant_id": tenant_id, "baseline_refreshed": True}


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
        result = {"campaign_id": campaign_id, "enriched_contacts": True}
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
        result = {"outreach_campaign_id": outreach_campaign_id, "step_executed": True}
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
        result = {"campaign_id": campaign_id, "submitted_batch": True}
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

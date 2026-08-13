from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.action_plan import ActionPlanMeasurement
from app.models.campaign import Campaign
from app.models.data_connection import DataConnection
from app.services import (
    crawl_service,
    data_connections_service,
    google_business_profile_service,
    job_service,
)
from app.services.audit_service import write_audit_log


COLLECTION_CONTRACT_VERSION = "wordpress-measurement-collection-v1"
ACTION_PLAN_MEASUREMENT_JOB_TYPE = "wordpress.post_change_measurement"
CRAWL_COLLECTION_JOB_TYPE = "wordpress.measurement_crawl"
MAX_COLLECTION_ATTEMPTS = 1
RECHECK_DELAY = timedelta(hours=2)

_SEARCH_METRICS = {
    "organic.ctr",
    "organic.impressions",
    "organic.avg_position",
}
_WEBSITE_PERFORMANCE_METRICS = {
    "cwv.lcp",
    "cwv.inp",
    "cwv.cls",
    "web_vital.ttfb",
}
_REVIEW_METRICS = {
    "local.review_velocity_30d",
    "local.avg_rating",
}
_BUSINESS_PROFILE_METRICS = {
    "local.gbp.total_appearances",
    "local.gbp.website_clicks",
    "local.gbp.call_clicks",
    "local.gbp.direction_requests",
    "local.gbp.bookings",
}


def schedule_minimum_collection(
    db: Session,
    *,
    measurement: ActionPlanMeasurement,
    readiness: dict[str, Any],
    collection_attempt: int = 0,
    requested_at: datetime | None = None,
) -> dict[str, Any]:
    """Refresh one primary result source without silently spending customer credits."""
    resolved_at = requested_at or datetime.now(UTC)
    primary_metric_id = str(readiness.get("primary_metric_id") or "").strip()
    if readiness.get("primary_metric_ready"):
        return _result(
            status="not_required",
            metric_id=primary_metric_id,
            message="The saved result is ready to compare.",
        )
    if not readiness.get("primary_baseline_ready"):
        return _save_result(
            db,
            measurement=measurement,
            result=_result(
                status="unavailable",
                metric_id=primary_metric_id or None,
                reason_code="wordpress_measurement_baseline_unavailable",
                message=(
                    "A trustworthy starting measurement was not saved before this change. "
                    "InsightOS cannot recreate it afterward, so no refresh or credits were used."
                ),
            ),
            requested_at=resolved_at,
        )
    if not primary_metric_id:
        return _save_result(
            db,
            measurement=measurement,
            result=_result(
                status="unavailable",
                metric_id=None,
                reason_code="wordpress_measurement_primary_metric_missing",
                message="This action does not name a primary result to refresh.",
            ),
            requested_at=resolved_at,
        )
    if collection_attempt >= MAX_COLLECTION_ATTEMPTS:
        return _save_result(
            db,
            measurement=measurement,
            result=_result(
                status="attempt_limit_reached",
                metric_id=primary_metric_id,
                reason_code="wordpress_measurement_collection_attempt_limit",
                message=(
                    "The connected source still has not published a comparable result. "
                    "InsightOS will report that honestly instead of spending more credits."
                ),
            ),
            requested_at=resolved_at,
        )

    campaign = db.get(Campaign, measurement.campaign_id)
    if (
        campaign is None
        or campaign.tenant_id != measurement.tenant_id
        or campaign.organization_id != measurement.organization_id
    ):
        return _save_result(
            db,
            measurement=measurement,
            result=_result(
                status="unavailable",
                metric_id=primary_metric_id,
                reason_code="wordpress_measurement_campaign_missing",
                message="The matching website could not be found for this result check.",
            ),
            requested_at=resolved_at,
        )

    collection_job = _create_collection_job(
        db,
        measurement=measurement,
        campaign=campaign,
        metric_id=primary_metric_id,
        attempt=collection_attempt + 1,
        requested_at=resolved_at,
    )
    if collection_job is None:
        return _save_result(
            db,
            measurement=measurement,
            result=_result(
                status="unavailable",
                metric_id=primary_metric_id,
                reason_code="wordpress_measurement_safe_collector_unavailable",
                message=(
                    "A safe included or connected-account refresh is not available for this "
                    "result. No Insight Credits were used."
                ),
            ),
            requested_at=resolved_at,
        )

    next_attempt = collection_attempt + 1
    recheck_at = resolved_at + RECHECK_DELAY
    recheck_job = job_service.create_job(
        db,
        tenant_id=measurement.tenant_id,
        job_type=ACTION_PLAN_MEASUREMENT_JOB_TYPE,
        entity_type="action_plan_measurement",
        entity_id=measurement.id,
        idempotency_key=(
            f"wordpress-post-change-measurement:{measurement.id}:"
            f"collection-attempt:{next_attempt}"
        ),
        payload={
            "tenant_id": measurement.tenant_id,
            "organization_id": measurement.organization_id,
            "campaign_id": measurement.campaign_id,
            "business_location_id": measurement.business_location_id,
            "occurrence_id": measurement.occurrence_id,
            "measurement_id": measurement.id,
            "due_at": recheck_at.isoformat(),
            "collection_attempt": next_attempt,
            "collection_job_id": collection_job.id,
            "contract_version": COLLECTION_CONTRACT_VERSION,
        },
        available_at=recheck_at,
        max_retries=2,
    )
    result = _result(
        status="scheduled",
        metric_id=primary_metric_id,
        message=(
            "InsightOS queued one included or connected-account refresh and will check "
            "the result again. No Insight Credits were used."
        ),
        collection_attempt=next_attempt,
        collection_job_id=collection_job.id,
        collection_job_type=collection_job.job_type,
        recheck_job_id=recheck_job.id,
        recheck_at=recheck_at.isoformat(),
    )
    return _save_result(
        db,
        measurement=measurement,
        result=result,
        requested_at=resolved_at,
    )


def _create_collection_job(
    db: Session,
    *,
    measurement: ActionPlanMeasurement,
    campaign: Campaign,
    metric_id: str,
    attempt: int,
    requested_at: datetime,
):
    scope = f"wordpress-measurement:{measurement.id}:{attempt}"
    if metric_id in _SEARCH_METRICS:
        connection = _connection(
            db,
            measurement=measurement,
            provider_name=data_connections_service.GOOGLE_SEARCH_CONSOLE_PROVIDER,
        )
        if connection is None:
            return None
        settings = get_settings()
        end_date = requested_at.date() - timedelta(
            days=max(0, int(settings.data_connection_sync_delay_days))
        )
        start_date = end_date - timedelta(
            days=max(0, int(measurement.observation_window_days) - 1)
        )
        return job_service.create_job(
            db,
            tenant_id=measurement.tenant_id,
            job_type="data_connections.search_console_sync",
            entity_type="data_connection",
            entity_id=connection.id,
            idempotency_key=f"{scope}:search-console",
            payload={
                "tenant_id": measurement.tenant_id,
                "organization_id": measurement.organization_id,
                "connection_id": connection.id,
                "campaign_id": measurement.campaign_id,
                "business_location_id": measurement.business_location_id,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "measurement_id": measurement.id,
                "credit_units": 0,
                "credential_owner": "organization",
            },
            available_at=requested_at,
            max_retries=2,
        )
    if metric_id in _WEBSITE_PERFORMANCE_METRICS:
        if not get_settings().crux_api_key.strip():
            return None
        form_factor = _baseline_form_factor(measurement)
        return job_service.create_job(
            db,
            tenant_id=measurement.tenant_id,
            job_type="website_performance.collect",
            entity_type="campaign",
            entity_id=campaign.id,
            idempotency_key=f"{scope}:website-performance:{form_factor}",
            payload={
                "tenant_id": measurement.tenant_id,
                "organization_id": measurement.organization_id,
                "campaign_id": measurement.campaign_id,
                "business_location_id": measurement.business_location_id,
                "form_factor": form_factor,
                "collection_date": requested_at.date().isoformat(),
                "measurement_scope": scope,
                "measurement_id": measurement.id,
                "credit_units": 0,
                "credential_owner": "platform_included",
            },
            available_at=requested_at,
            max_retries=2,
        )
    if metric_id in _REVIEW_METRICS | _BUSINESS_PROFILE_METRICS:
        connection = _connection(
            db,
            measurement=measurement,
            provider_name=google_business_profile_service.GOOGLE_BUSINESS_PROFILE_PROVIDER,
        )
        if connection is None:
            return None
        job_type = (
            "reputation.owned_reviews_sync"
            if metric_id in _REVIEW_METRICS
            else "data_connections.google_business_profile_sync"
        )
        payload = {
            "tenant_id": measurement.tenant_id,
            "organization_id": measurement.organization_id,
            "connection_id": connection.id,
            "campaign_id": measurement.campaign_id,
            "business_location_id": measurement.business_location_id,
            "measurement_id": measurement.id,
            "credit_units": 0,
            "credential_owner": "organization",
        }
        if metric_id in _BUSINESS_PROFILE_METRICS:
            end_date = requested_at.date() - timedelta(days=3)
            payload.update(
                {
                    "start_date": (
                        end_date
                        - timedelta(days=max(0, int(measurement.observation_window_days) - 1))
                    ).isoformat(),
                    "end_date": end_date.isoformat(),
                }
            )
        return job_service.create_job(
            db,
            tenant_id=measurement.tenant_id,
            job_type=job_type,
            entity_type="data_connection",
            entity_id=connection.id,
            idempotency_key=f"{scope}:{job_type}",
            payload=payload,
            available_at=requested_at,
            max_retries=2,
        )
    if metric_id == "technical.issue_density":
        seed_url = str(campaign.domain or "").strip()
        if not seed_url:
            return None
        if not seed_url.startswith(("http://", "https://")):
            seed_url = f"https://{seed_url}"
        run = crawl_service.schedule_crawl(
            db,
            tenant_id=measurement.tenant_id,
            campaign_id=measurement.campaign_id,
            crawl_type="delta",
            seed_url=seed_url,
        )
        return job_service.create_job(
            db,
            tenant_id=measurement.tenant_id,
            job_type=CRAWL_COLLECTION_JOB_TYPE,
            entity_type="crawl_run",
            entity_id=run.id,
            idempotency_key=f"{scope}:crawl",
            payload={
                "tenant_id": measurement.tenant_id,
                "organization_id": measurement.organization_id,
                "campaign_id": measurement.campaign_id,
                "business_location_id": measurement.business_location_id,
                "crawl_run_id": run.id,
                "measurement_id": measurement.id,
                "credit_units": 0,
                "usage_control": "monthly_crawl_page_allowance",
                "planned_pages": 1,
            },
            available_at=requested_at,
            max_retries=2,
        )
    return None


def _connection(
    db: Session,
    *,
    measurement: ActionPlanMeasurement,
    provider_name: str,
) -> DataConnection | None:
    query = db.query(DataConnection).filter(
        DataConnection.tenant_id == measurement.tenant_id,
        DataConnection.organization_id == measurement.organization_id,
        DataConnection.campaign_id == measurement.campaign_id,
        DataConnection.provider_name == provider_name,
        DataConnection.status != data_connections_service.CONNECTION_STATUS_DISCONNECTED,
    )
    if measurement.business_location_id:
        query = query.filter(
            DataConnection.business_location_id == measurement.business_location_id
        )
    return query.order_by(DataConnection.last_success_at.desc(), DataConnection.created_at.asc()).first()


def _baseline_form_factor(measurement: ActionPlanMeasurement) -> str:
    primary_metric_id = str((measurement.success_metric_ids or [""])[0])
    primary = next(
        (
            item
            for item in measurement.baseline_metrics or []
            if str(item.get("metric_id") or "") == primary_metric_id
        ),
        {},
    )
    form_factor = str((primary.get("entity_scope") or {}).get("form_factor") or "mobile")
    return form_factor if form_factor in {"mobile", "desktop"} else "mobile"


def _result(
    *,
    status: str,
    metric_id: str | None,
    message: str,
    reason_code: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "contract_version": COLLECTION_CONTRACT_VERSION,
        "status": status,
        "primary_metric_id": metric_id,
        "reason_code": reason_code,
        "message": message,
        "credits_reserved": 0,
        "paid_provider_calls_allowed": False,
        "collection_scope": "primary_metric_only",
        **extra,
    }


def _save_result(
    db: Session,
    *,
    measurement: ActionPlanMeasurement,
    result: dict[str, Any],
    requested_at: datetime,
) -> dict[str, Any]:
    contract = dict(measurement.measurement_contract or {})
    history = list(contract.get("source_refresh_history") or [])
    history.append({**result, "requested_at": requested_at.isoformat()})
    contract["source_refresh_history"] = history[-5:]
    contract["latest_source_refresh"] = history[-1]
    measurement.measurement_contract = contract
    measurement.updated_at = requested_at
    write_audit_log(
        db,
        tenant_id=measurement.tenant_id,
        actor_user_id="InsightOS measurement scheduler",
        event_type="wordpress.post_change_measurement.source_refresh",
        payload={
            "organization_id": measurement.organization_id,
            "campaign_id": measurement.campaign_id,
            "occurrence_id": measurement.occurrence_id,
            "measurement_id": measurement.id,
            **result,
        },
    )
    db.flush()
    return result

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.intelligence.lexicon import get_active_lexicon
from app.models.action_plan import ActionPlanMeasurement, ActionPlanOccurrence, ActionPlanStep
from app.models.campaign import Campaign
from app.models.content import ContentAsset
from app.models.crawl import CrawlPageResult, CrawlRun, TechnicalIssue
from app.models.intelligence import StrategyRecommendation
from app.models.local import ReviewVelocitySnapshot
from app.models.search_console_daily_metric import SearchConsoleDailyMetric
from app.models.website_performance import WebsitePerformanceMeasurement


_DEFAULT_DIRECTIONS = {
    "organic.avg_position": "lower_is_better",
    "local.avg_rating": "higher_is_better",
    "technical.issue_density": "lower_is_better",
    "technical.crawl_health": "higher_is_better",
}
_WEBSITE_COLUMNS = {
    "cwv.lcp": "lcp_ms",
    "cwv.inp": "inp_ms",
    "cwv.cls": "cls_value",
    "web_vital.ttfb": "ttfb_ms",
}


def _as_aware(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=UTC)


def _iso(value: datetime | date | None) -> str | None:
    return value.isoformat() if value is not None else None


def _parse_evidence(recommendation: StrategyRecommendation) -> tuple[list[str], list[str]]:
    try:
        payload = json.loads(recommendation.evidence_json or "{}")
    except json.JSONDecodeError:
        payload = {}
    evidence: list[str] = []
    affected_urls: list[str] = []
    if isinstance(payload, list):
        evidence = [str(item) for item in payload]
    elif isinstance(payload, dict):
        raw_evidence = payload.get("evidence")
        if isinstance(raw_evidence, list):
            evidence = [str(item) for item in raw_evidence]
        for key in ("affected_urls", "urls", "pages"):
            values = payload.get(key)
            if isinstance(values, list):
                affected_urls.extend(str(item) for item in values if item)
        for key in ("url", "page_url", "affected_url"):
            value = payload.get(key)
            if value:
                affected_urls.append(str(value))
    return list(dict.fromkeys(evidence)), list(dict.fromkeys(affected_urls))


def _metric_shell(metric: Any) -> dict[str, Any]:
    thresholds = metric.thresholds
    direction = (
        str(thresholds.direction)
        if thresholds is not None
        else _DEFAULT_DIRECTIONS.get(metric.metric_id)
    )
    return {
        "metric_id": metric.metric_id,
        "display_name": metric.display_name,
        "plain_language": metric.plain_language,
        "unit": metric.unit,
        "aggregation": metric.aggregation,
        "direction": direction,
        "status": "insufficient_data",
        "value": None,
        "source": None,
        "source_record_id": None,
        "measured_at": None,
        "evidence_window_start": None,
        "evidence_window_end": None,
        "scope": str(metric.scope),
    }


def _website_metric(
    db: Session,
    *,
    tenant_id: str,
    campaign_id: str,
    metric: Any,
    captured_at: datetime,
) -> dict[str, Any]:
    payload = _metric_shell(metric)
    column_name = _WEBSITE_COLUMNS[metric.metric_id]
    column = getattr(WebsitePerformanceMeasurement, column_name)
    row = (
        db.query(WebsitePerformanceMeasurement)
        .filter(
            WebsitePerformanceMeasurement.tenant_id == tenant_id,
            WebsitePerformanceMeasurement.campaign_id == campaign_id,
            WebsitePerformanceMeasurement.source == "crux_field",
            WebsitePerformanceMeasurement.status == "ready",
            WebsitePerformanceMeasurement.captured_at <= captured_at,
            column.isnot(None),
        )
        .order_by(WebsitePerformanceMeasurement.captured_at.desc())
        .first()
    )
    if row is None:
        return payload
    payload.update(
        {
            "status": "available",
            "value": float(getattr(row, column_name)),
            "source": "Chrome UX Report field data",
            "source_record_id": row.id,
            "measured_at": _iso(row.captured_at),
            "evidence_window_start": _iso(row.collection_start),
            "evidence_window_end": _iso(row.collection_end),
            "scope": f"{row.scope}:{row.form_factor}",
            "measured_url": row.measured_url,
        }
    )
    return payload


def _search_metric(
    db: Session,
    *,
    campaign_id: str,
    metric: Any,
    captured_at: datetime,
) -> dict[str, Any]:
    payload = _metric_shell(metric)
    row = (
        db.query(SearchConsoleDailyMetric)
        .filter(
            SearchConsoleDailyMetric.campaign_id == campaign_id,
            SearchConsoleDailyMetric.metric_date <= captured_at.date(),
        )
        .order_by(SearchConsoleDailyMetric.metric_date.desc())
        .first()
    )
    if row is None:
        return payload
    value: float | None = None
    if metric.metric_id == "organic.ctr" and row.impressions > 0:
        value = float(row.clicks) / float(row.impressions)
    elif metric.metric_id == "organic.impressions":
        value = float(row.impressions)
    elif metric.metric_id == "organic.avg_position" and row.avg_position is not None:
        value = float(row.avg_position)
    if value is None:
        return payload
    payload.update(
        {
            "status": "available",
            "value": value,
            "source": "Google Search Console",
            "source_record_id": row.id,
            "measured_at": _iso(row.metric_date),
            "evidence_window_start": _iso(row.metric_date),
            "evidence_window_end": _iso(row.metric_date),
        }
    )
    return payload


def _review_metric(
    db: Session,
    *,
    tenant_id: str,
    campaign_id: str,
    metric: Any,
    captured_at: datetime,
) -> dict[str, Any]:
    payload = _metric_shell(metric)
    row = (
        db.query(ReviewVelocitySnapshot)
        .filter(
            ReviewVelocitySnapshot.tenant_id == tenant_id,
            ReviewVelocitySnapshot.campaign_id == campaign_id,
            ReviewVelocitySnapshot.captured_at <= captured_at,
        )
        .order_by(ReviewVelocitySnapshot.captured_at.desc())
        .first()
    )
    if row is None:
        return payload
    if metric.metric_id == "local.review_velocity_30d":
        value = float(row.reviews_last_30d)
    elif metric.metric_id == "local.avg_rating":
        value = float(row.avg_rating_last_30d)
    else:
        return payload
    captured_at = _as_aware(row.captured_at)
    payload.update(
        {
            "status": "available",
            "value": value,
            "source": "Stored Google review measurements",
            "source_record_id": row.id,
            "measured_at": _iso(captured_at),
            "evidence_window_start": _iso(
                captured_at - timedelta(days=30) if captured_at else None
            ),
            "evidence_window_end": _iso(captured_at),
        }
    )
    return payload


def _technical_issue_density(
    db: Session,
    *,
    tenant_id: str,
    campaign_id: str,
    metric: Any,
    captured_at: datetime,
) -> dict[str, Any]:
    payload = _metric_shell(metric)
    crawl = (
        db.query(CrawlRun)
        .filter(
            CrawlRun.tenant_id == tenant_id,
            CrawlRun.campaign_id == campaign_id,
            CrawlRun.status == "completed",
            CrawlRun.created_at <= captured_at,
        )
        .order_by(CrawlRun.finished_at.desc(), CrawlRun.created_at.desc())
        .first()
    )
    if crawl is None:
        return payload
    page_count = (
        db.query(func.count(CrawlPageResult.id))
        .filter(CrawlPageResult.crawl_run_id == crawl.id)
        .scalar()
        or 0
    )
    if page_count <= 0:
        return payload
    issue_count = (
        db.query(func.count(TechnicalIssue.id))
        .filter(TechnicalIssue.crawl_run_id == crawl.id)
        .scalar()
        or 0
    )
    measured_at = _as_aware(crawl.finished_at or crawl.created_at)
    payload.update(
        {
            "status": "available",
            "value": float(issue_count) / float(page_count),
            "source": "Stored website crawl",
            "source_record_id": crawl.id,
            "measured_at": _iso(measured_at),
            "evidence_window_start": _iso(_as_aware(crawl.started_at or crawl.created_at)),
            "evidence_window_end": _iso(measured_at),
            "pages_checked": int(page_count),
            "issues_found": int(issue_count),
        }
    )
    return payload


def _content_growth(
    db: Session,
    *,
    tenant_id: str,
    campaign_id: str,
    metric: Any,
    captured_at: datetime,
) -> dict[str, Any]:
    payload = _metric_shell(metric)
    current_start = captured_at - timedelta(days=30)
    previous_start = captured_at - timedelta(days=60)
    published = {"published", "live"}
    current_count = (
        db.query(func.count(ContentAsset.id))
        .filter(
            ContentAsset.tenant_id == tenant_id,
            ContentAsset.campaign_id == campaign_id,
            ContentAsset.status.in_(published),
            ContentAsset.created_at >= current_start,
            ContentAsset.created_at <= captured_at,
        )
        .scalar()
        or 0
    )
    previous_count = (
        db.query(func.count(ContentAsset.id))
        .filter(
            ContentAsset.tenant_id == tenant_id,
            ContentAsset.campaign_id == campaign_id,
            ContentAsset.status.in_(published),
            ContentAsset.created_at >= previous_start,
            ContentAsset.created_at < current_start,
        )
        .scalar()
        or 0
    )
    if previous_count <= 0:
        return payload
    payload.update(
        {
            "status": "available",
            "value": (float(current_count) - float(previous_count)) / float(previous_count),
            "source": "Stored published content",
            "source_record_id": None,
            "measured_at": _iso(captured_at),
            "evidence_window_start": _iso(previous_start),
            "evidence_window_end": _iso(captured_at),
            "current_30_day_count": int(current_count),
            "previous_30_day_count": int(previous_count),
        }
    )
    return payload


def _capture_metric(
    db: Session,
    *,
    tenant_id: str,
    campaign_id: str,
    metric: Any,
    captured_at: datetime,
) -> dict[str, Any]:
    if metric.metric_id in _WEBSITE_COLUMNS:
        return _website_metric(
            db,
            tenant_id=tenant_id,
            campaign_id=campaign_id,
            metric=metric,
            captured_at=captured_at,
        )
    if metric.metric_id in {"organic.ctr", "organic.impressions", "organic.avg_position"}:
        return _search_metric(
            db,
            campaign_id=campaign_id,
            metric=metric,
            captured_at=captured_at,
        )
    if metric.metric_id in {"local.review_velocity_30d", "local.avg_rating"}:
        return _review_metric(
            db,
            tenant_id=tenant_id,
            campaign_id=campaign_id,
            metric=metric,
            captured_at=captured_at,
        )
    if metric.metric_id == "technical.issue_density":
        return _technical_issue_density(
            db,
            tenant_id=tenant_id,
            campaign_id=campaign_id,
            metric=metric,
            captured_at=captured_at,
        )
    if metric.metric_id == "content.growth_rate":
        return _content_growth(
            db,
            tenant_id=tenant_id,
            campaign_id=campaign_id,
            metric=metric,
            captured_at=captured_at,
        )
    return _metric_shell(metric)


def _window_bounds(metrics: list[dict[str, Any]]) -> tuple[datetime | None, datetime | None]:
    starts: list[datetime] = []
    ends: list[datetime] = []
    for metric in metrics:
        for key, target in (("evidence_window_start", starts), ("evidence_window_end", ends)):
            value = metric.get(key)
            if not value:
                continue
            try:
                parsed = datetime.fromisoformat(str(value))
            except ValueError:
                try:
                    parsed = datetime.combine(date.fromisoformat(str(value)), datetime.min.time(), UTC)
                except ValueError:
                    continue
            target.append(_as_aware(parsed) or parsed)
    return (min(starts) if starts else None, max(ends) if ends else None)


def capture_action_plan_baseline(
    db: Session,
    *,
    occurrence: ActionPlanOccurrence,
    captured_at: datetime | None = None,
) -> ActionPlanMeasurement:
    existing = (
        db.query(ActionPlanMeasurement)
        .filter(ActionPlanMeasurement.occurrence_id == occurrence.id)
        .first()
    )
    if existing is not None:
        return existing

    resolved_at = captured_at or datetime.now(UTC)
    lexicon = get_active_lexicon(db, tenant_id=occurrence.tenant_id)
    action = lexicon.action_index.get(occurrence.action_id)
    recommendation = db.get(StrategyRecommendation, occurrence.recommendation_id)
    campaign = db.get(Campaign, occurrence.campaign_id)
    if action is None or recommendation is None or campaign is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The saved action plan can no longer be matched to its measurement rules.",
        )

    metrics = [
        _capture_metric(
            db,
            tenant_id=occurrence.tenant_id,
            campaign_id=occurrence.campaign_id,
            metric=lexicon.metric_index[metric_id],
            captured_at=resolved_at,
        )
        for metric_id in action.success_metric_ids
    ]
    evidence, affected_urls = _parse_evidence(recommendation)
    measured_urls = [
        str(item["measured_url"])
        for item in metrics
        if item.get("measured_url")
    ]
    window_start, window_end = _window_bounds(metrics)
    has_baseline = any(item.get("status") == "available" for item in metrics)
    row = ActionPlanMeasurement(
        tenant_id=occurrence.tenant_id,
        organization_id=occurrence.organization_id,
        campaign_id=occurrence.campaign_id,
        business_location_id=occurrence.business_location_id,
        occurrence_id=occurrence.id,
        recommendation_id=occurrence.recommendation_id,
        action_id=occurrence.action_id,
        measurement_status="baseline_ready" if has_baseline else "insufficient_baseline",
        outcome_status="pending",
        success_metric_ids=list(action.success_metric_ids),
        baseline_metrics=metrics,
        baseline_evidence=evidence,
        implementation_scope={
            "campaign_id": occurrence.campaign_id,
            "business_location_id": occurrence.business_location_id,
            "domain": campaign.domain,
            "affected_urls": list(dict.fromkeys(affected_urls + measured_urls)),
            "action_id": occurrence.action_id,
        },
        completion_proof=[],
        outcome_metrics=[],
        outcome_evidence=[],
        observation_window_days=int(action.observation_window_days),
        evidence_window_start=window_start,
        evidence_window_end=window_end,
        observation_due_at=None,
        baseline_captured_at=resolved_at,
        work_completed_at=None,
        outcome_measured_at=None,
        action_plan_hash=occurrence.content_hash,
        lexicon_id=occurrence.lexicon_id,
        lexicon_version=occurrence.lexicon_version,
        created_at=resolved_at,
        updated_at=resolved_at,
    )
    db.add(row)
    db.flush()
    return row


def mark_action_plan_work_completed(
    db: Session,
    *,
    occurrence: ActionPlanOccurrence,
    steps: list[ActionPlanStep],
    completed_at: datetime,
) -> ActionPlanMeasurement:
    measurement = capture_action_plan_baseline(
        db,
        occurrence=occurrence,
        captured_at=completed_at,
    )
    measurement.completion_proof = [
        {
            "step_id": step.id,
            "step_key": step.step_key,
            "instruction": step.instruction,
            "status": step.status,
            "evidence": list(step.evidence or []),
            "completed_by_user_id": step.completed_by_user_id,
            "completed_at": _iso(step.completed_at),
        }
        for step in steps
        if step.required
    ]
    measurement.work_completed_at = completed_at
    measurement.observation_due_at = completed_at + timedelta(
        days=measurement.observation_window_days
    )
    measurement.measurement_status = "waiting_for_results"
    measurement.outcome_status = "pending"
    measurement.outcome_metrics = []
    measurement.outcome_evidence = []
    measurement.outcome_measured_at = None
    measurement.updated_at = completed_at
    db.flush()
    return measurement


def mark_action_plan_work_reopened(
    db: Session,
    *,
    occurrence: ActionPlanOccurrence,
    reopened_at: datetime,
) -> None:
    measurement = (
        db.query(ActionPlanMeasurement)
        .filter(ActionPlanMeasurement.occurrence_id == occurrence.id)
        .first()
    )
    if measurement is None or measurement.measurement_status == "measured":
        return
    measurement.measurement_status = (
        "baseline_ready"
        if any(item.get("status") == "available" for item in measurement.baseline_metrics or [])
        else "insufficient_baseline"
    )
    measurement.work_completed_at = None
    measurement.observation_due_at = None
    measurement.completion_proof = []
    measurement.updated_at = reopened_at
    db.flush()


def _comparison(
    baseline: dict[str, Any],
    observed: dict[str, Any],
    *,
    work_completed_at: datetime | None,
) -> dict[str, Any]:
    result = dict(observed)
    before = baseline.get("value")
    after = observed.get("value")
    direction = baseline.get("direction")
    same_source_record = bool(
        baseline.get("source_record_id")
        and baseline.get("source_record_id") == observed.get("source_record_id")
    )
    observed_at: datetime | None = None
    if observed.get("measured_at"):
        try:
            observed_at = _as_aware(datetime.fromisoformat(str(observed["measured_at"])))
        except ValueError:
            observed_at = None
    completed_at = _as_aware(work_completed_at)
    not_newer_than_work = bool(
        observed_at is not None
        and completed_at is not None
        and observed_at <= completed_at
    )
    if (
        before is None
        or after is None
        or direction not in {"higher_is_better", "lower_is_better"}
        or same_source_record
        or not_newer_than_work
    ):
        result.update({"baseline_value": before, "change": None, "comparison": "insufficient_data"})
        return result
    delta = float(after) - float(before)
    tolerance = max(abs(float(before)) * 0.005, 0.000001)
    if abs(delta) <= tolerance:
        comparison = "unchanged"
    elif (direction == "higher_is_better" and delta > 0) or (
        direction == "lower_is_better" and delta < 0
    ):
        comparison = "improved"
    else:
        comparison = "worse"
    result.update(
        {
            "baseline_value": float(before),
            "change": delta,
            "comparison": comparison,
        }
    )
    return result


def evaluate_action_plan_outcome(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
    occurrence_id: str,
    measured_at: datetime | None = None,
) -> dict[str, Any]:
    occurrence = (
        db.query(ActionPlanOccurrence)
        .filter(
            ActionPlanOccurrence.id == occurrence_id,
            ActionPlanOccurrence.tenant_id == tenant_id,
            ActionPlanOccurrence.organization_id == organization_id,
            ActionPlanOccurrence.campaign_id == campaign_id,
        )
        .with_for_update()
        .first()
    )
    if occurrence is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action plan not found")
    measurement = (
        db.query(ActionPlanMeasurement)
        .filter(
            ActionPlanMeasurement.tenant_id == tenant_id,
            ActionPlanMeasurement.organization_id == organization_id,
            ActionPlanMeasurement.occurrence_id == occurrence_id,
        )
        .first()
    )
    if measurement is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Start the checklist before checking results.",
        )
    if measurement.measurement_status == "measured":
        return serialize_action_plan_measurement(measurement, now=measured_at)
    if occurrence.status != "waiting_for_results" or measurement.work_completed_at is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Finish every required checklist step before checking results.",
        )

    resolved_at = measured_at or datetime.now(UTC)
    due_at = _as_aware(measurement.observation_due_at)
    if due_at is not None and resolved_at < due_at:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Results can be checked after {due_at.isoformat()}.",
        )

    lexicon = get_active_lexicon(db, tenant_id=tenant_id)
    baseline_by_id = {
        str(item.get("metric_id")): item for item in measurement.baseline_metrics or []
    }
    outcome_metrics: list[dict[str, Any]] = []
    for metric_id in measurement.success_metric_ids or []:
        metric = lexicon.metric_index.get(str(metric_id))
        if metric is None:
            continue
        observed = _capture_metric(
            db,
            tenant_id=tenant_id,
            campaign_id=campaign_id,
            metric=metric,
            captured_at=resolved_at,
        )
        outcome_metrics.append(
            _comparison(
                baseline_by_id.get(str(metric_id), {}),
                observed,
                work_completed_at=measurement.work_completed_at,
            )
        )

    comparisons = {
        str(item.get("comparison"))
        for item in outcome_metrics
        if item.get("comparison") not in {None, "insufficient_data"}
    }
    if not comparisons:
        outcome_status = "insufficient_data"
    elif "improved" in comparisons and "worse" not in comparisons:
        outcome_status = "helped"
    else:
        outcome_status = "did_not_help"

    measurement.measurement_status = "measured"
    measurement.outcome_status = outcome_status
    measurement.outcome_metrics = outcome_metrics
    measurement.outcome_evidence = [
        {
            "metric_id": item.get("metric_id"),
            "source": item.get("source"),
            "source_record_id": item.get("source_record_id"),
            "measured_at": item.get("measured_at"),
        }
        for item in outcome_metrics
        if item.get("source")
    ]
    measurement.outcome_measured_at = resolved_at
    measurement.updated_at = resolved_at
    occurrence.status = "completed"
    occurrence.updated_at = resolved_at
    db.commit()
    db.refresh(measurement)
    return serialize_action_plan_measurement(measurement, now=resolved_at)


def get_action_plan_measurement(
    db: Session,
    *,
    occurrence_id: str,
) -> ActionPlanMeasurement | None:
    return (
        db.query(ActionPlanMeasurement)
        .filter(ActionPlanMeasurement.occurrence_id == occurrence_id)
        .first()
    )


def serialize_action_plan_measurement(
    measurement: ActionPlanMeasurement,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    resolved_now = now or datetime.now(UTC)
    due_at = _as_aware(measurement.observation_due_at)
    if measurement.measurement_status == "measured":
        readiness = "measured"
    elif due_at is not None and resolved_now >= due_at:
        readiness = "ready_to_check"
    elif due_at is not None:
        readiness = "waiting"
    elif measurement.measurement_status == "insufficient_baseline":
        readiness = "baseline_unavailable"
    else:
        readiness = "work_in_progress"
    available_count = sum(
        item.get("status") == "available" for item in measurement.baseline_metrics or []
    )
    return {
        "id": measurement.id,
        "measurement_status": measurement.measurement_status,
        "readiness": readiness,
        "outcome_status": measurement.outcome_status,
        "success_metric_ids": list(measurement.success_metric_ids or []),
        "baseline_metrics": list(measurement.baseline_metrics or []),
        "baseline_available_count": available_count,
        "baseline_evidence": list(measurement.baseline_evidence or []),
        "implementation_scope": dict(measurement.implementation_scope or {}),
        "completion_proof": list(measurement.completion_proof or []),
        "outcome_metrics": list(measurement.outcome_metrics or []),
        "outcome_evidence": list(measurement.outcome_evidence or []),
        "observation_window_days": measurement.observation_window_days,
        "evidence_window": {
            "start": _iso(measurement.evidence_window_start),
            "end": _iso(measurement.evidence_window_end),
        },
        "observation_due_at": _iso(due_at),
        "baseline_captured_at": _iso(measurement.baseline_captured_at),
        "work_completed_at": _iso(measurement.work_completed_at),
        "outcome_measured_at": _iso(measurement.outcome_measured_at),
        "action_plan_hash": measurement.action_plan_hash,
        "lexicon_id": measurement.lexicon_id,
        "lexicon_version": measurement.lexicon_version,
    }

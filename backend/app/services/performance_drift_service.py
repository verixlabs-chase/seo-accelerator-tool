from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from hashlib import sha256
import json
import math
from statistics import median
from typing import Any, Iterable

from sqlalchemy.orm import Session

from app.models.campaign import Campaign
from app.models.reference_library import StandardsChangeCandidate
from app.models.search_console_daily_metric import SearchConsoleDailyMetric
from app.models.standards_governance import PerformanceDriftEvent
from app.services import standards_source_service
from app.services.audit_service import write_audit_log


DETECTOR_VERSION = "i1.6f.v1"
DEFAULT_PERIOD_DAYS = 14
DEFAULT_MINIMUM_ORGANIZATIONS = 5
DEFAULT_MINIMUM_COVERAGE = 0.80
DEFAULT_AGREEMENT_RATIO = 0.75
SUPPORTED_SEARCH_CONSOLE_METRICS: dict[str, dict[str, Any]] = {
    "clicks": {
        "contract_id": "search_console.clicks",
        "metric_family": "search_console_clicks",
        "display_name": "website visits from Google Search",
        "threshold": 0.20,
        "change_mode": "relative",
    },
    "impressions": {
        "contract_id": "search_console.impressions",
        "metric_family": "search_console_impressions",
        "display_name": "appearances in Google Search",
        "threshold": 0.20,
        "change_mode": "relative",
    },
    "avg_position": {
        "contract_id": "search_console.position",
        "metric_family": "search_console_position",
        "display_name": "average Google position number",
        "threshold": 1.0,
        "change_mode": "absolute",
        "lower_is_better": True,
    },
}
REVIEW_STATUSES = frozenset({"investigating", "dismissed", "resolved"})


@dataclass(frozen=True)
class MinimizedDriftObservation:
    organization_key: str
    sample_key: str
    baseline_value: float
    comparison_value: float


def run_search_console_drift_check(
    db: Session,
    *,
    metrics: Iterable[str] | None = None,
    period_days: int = DEFAULT_PERIOD_DAYS,
    as_of: date | None = None,
    minimum_organizations: int = DEFAULT_MINIMUM_ORGANIZATIONS,
    actor_user_id: str | None = None,
    audit_tenant_id: str | None = None,
) -> dict[str, Any]:
    """Evaluate comparable Search Console cohorts without persisting member IDs."""

    resolved_metrics = tuple(dict.fromkeys(metrics or SUPPORTED_SEARCH_CONSOLE_METRICS))
    unknown = sorted(set(resolved_metrics) - set(SUPPORTED_SEARCH_CONSOLE_METRICS))
    if unknown:
        raise ValueError(f"Unsupported drift metrics: {', '.join(unknown)}")
    resolved_period_days = max(7, min(int(period_days), 90))
    resolved_minimum = max(5, min(int(minimum_organizations), 100))

    try:
        standards_source_service.assert_provider_contract_ready(db, "google_search_console")
    except standards_source_service.StandardsContractBlockedError as exc:
        return {
            "status": "confounded",
            "checked_at": datetime.now(UTC),
            "detector_version": DETECTOR_VERSION,
            "events": [],
            "results": [],
            "known_confounders": [
                {
                    "code": "provider_contract_under_review",
                    "message": "Search Console definitions are under review, so shared movement was not evaluated.",
                    "change_candidate_id": exc.candidate_id,
                }
            ],
            "automatic_activation_allowed": False,
        }

    latest_date = as_of or db.query(SearchConsoleDailyMetric.metric_date).order_by(
        SearchConsoleDailyMetric.metric_date.desc()
    ).limit(1).scalar()
    if latest_date is None:
        return _empty_check("no_data", resolved_period_days, resolved_minimum)

    comparison_end = latest_date
    comparison_start = comparison_end - timedelta(days=resolved_period_days - 1)
    baseline_end = comparison_start - timedelta(days=1)
    baseline_start = baseline_end - timedelta(days=resolved_period_days - 1)
    incident_confounders = _search_status_confounders(
        db, start=baseline_start, end=comparison_end
    )
    if incident_confounders:
        return {
            "status": "confounded",
            "checked_at": datetime.now(UTC),
            "detector_version": DETECTOR_VERSION,
            "events": [],
            "results": [],
            "known_confounders": incident_confounders,
            "periods": _period_payload(
                baseline_start, baseline_end, comparison_start, comparison_end
            ),
            "automatic_activation_allowed": False,
        }

    rows = (
        db.query(SearchConsoleDailyMetric)
        .filter(
            SearchConsoleDailyMetric.metric_date >= baseline_start,
            SearchConsoleDailyMetric.metric_date <= comparison_end,
        )
        .order_by(
            SearchConsoleDailyMetric.organization_id,
            SearchConsoleDailyMetric.campaign_id,
            SearchConsoleDailyMetric.metric_date,
        )
        .all()
    )
    campaign_ids = {row.campaign_id for row in rows}
    campaign_created = {
        row.id: row.created_at.date()
        for row in db.query(Campaign).filter(Campaign.id.in_(campaign_ids)).all()
    } if campaign_ids else {}

    check_results: list[dict[str, Any]] = []
    event_payloads: list[dict[str, Any]] = []
    for metric_name in resolved_metrics:
        config = SUPPORTED_SEARCH_CONSOLE_METRICS[metric_name]
        cohort_samples, excluded = _cohort_samples(
            rows,
            metric_name=metric_name,
            contract_id=config["contract_id"],
            baseline_start=baseline_start,
            baseline_end=baseline_end,
            comparison_start=comparison_start,
            comparison_end=comparison_end,
            period_days=resolved_period_days,
            campaign_created=campaign_created,
        )
        if not cohort_samples:
            check_results.append(
                {
                    "metric": metric_name,
                    "status": "insufficient_sample",
                    "eligible_samples": 0,
                    "excluded_samples": excluded,
                    "minimum_organizations": resolved_minimum,
                }
            )
            continue

        for (contract_version, scope_hash), observations in sorted(cohort_samples.items()):
            analysis = analyze_minimized_cohort(
                observations,
                metric_name=metric_name,
                minimum_organizations=resolved_minimum,
            )
            result = {
                "metric": metric_name,
                "metric_contract_id": config["contract_id"],
                "metric_contract_version": contract_version,
                "comparison_scope_hash": scope_hash,
                "excluded_samples": excluded,
                **analysis,
            }
            check_results.append(result)
            if analysis["status"] != "signal_detected":
                continue
            evidence_digest = _evidence_digest(observations, metric_name, scope_hash)
            existing = (
                db.query(PerformanceDriftEvent)
                .filter(
                    PerformanceDriftEvent.detector_version == DETECTOR_VERSION,
                    PerformanceDriftEvent.metric_contract_id == config["contract_id"],
                    PerformanceDriftEvent.comparison_scope_hash == scope_hash,
                    PerformanceDriftEvent.comparison_end == comparison_end,
                    PerformanceDriftEvent.evidence_digest == evidence_digest,
                )
                .one_or_none()
            )
            event = existing or PerformanceDriftEvent(
                detector_version=DETECTOR_VERSION,
                label="possible_ecosystem_change",
                status="needs_review",
                provider_name="google_search_console",
                metric_family=config["metric_family"],
                metric_contract_id=config["contract_id"],
                metric_contract_version=contract_version,
                comparison_scope_hash=scope_hash,
                baseline_start=baseline_start,
                baseline_end=baseline_end,
                comparison_start=comparison_start,
                comparison_end=comparison_end,
                sample_size=analysis["sample_size"],
                organization_count=analysis["organization_count"],
                excluded_sample_size=excluded,
                direction=analysis["direction"],
                median_change=analysis["median_change"],
                confidence_low=analysis["confidence_low"],
                confidence_high=analysis["confidence_high"],
                agreement_ratio=analysis["agreement_ratio"],
                cohort_rules={
                    "period_days": resolved_period_days,
                    "minimum_organizations": resolved_minimum,
                    "minimum_daily_coverage": DEFAULT_MINIMUM_COVERAGE,
                    "minimum_direction_agreement": DEFAULT_AGREEMENT_RATIO,
                    "metric_threshold": config["threshold"],
                    "comparison_requires_same_contract_version": True,
                    "comparison_requires_same_scope": True,
                    "organization_weighting": "equal_weight_after_location_median",
                },
                known_confounders=[],
                affected_metric_families=[config["metric_family"]],
                evidence_digest=evidence_digest,
                plain_language_summary=_plain_language_summary(
                    config,
                    analysis["direction"],
                    analysis["median_change"],
                    analysis["organization_count"],
                ),
                automatic_activation_allowed=False,
            )
            if existing is None:
                db.add(event)
                db.flush()
                if actor_user_id and audit_tenant_id:
                    write_audit_log(
                        db,
                        tenant_id=audit_tenant_id,
                        actor_user_id=actor_user_id,
                        event_type="standards.performance_drift.detected",
                        payload={
                            "performance_drift_event_id": event.id,
                            "metric_contract_id": event.metric_contract_id,
                            "metric_contract_version": event.metric_contract_version,
                            "comparison_end": event.comparison_end.isoformat(),
                            "sample_size": event.sample_size,
                            "organization_count": event.organization_count,
                            "automatic_activation_allowed": False,
                        },
                    )
            event_payloads.append(_event_payload(event))

    db.commit()
    return {
        "status": "completed",
        "checked_at": datetime.now(UTC),
        "detector_version": DETECTOR_VERSION,
        "periods": _period_payload(
            baseline_start, baseline_end, comparison_start, comparison_end
        ),
        "results": check_results,
        "events": event_payloads,
        "known_confounders": [],
        "automatic_activation_allowed": False,
    }


def analyze_minimized_cohort(
    observations: Iterable[MinimizedDriftObservation],
    *,
    metric_name: str,
    minimum_organizations: int = DEFAULT_MINIMUM_ORGANIZATIONS,
) -> dict[str, Any]:
    config = SUPPORTED_SEARCH_CONSOLE_METRICS.get(metric_name)
    if config is None:
        raise ValueError(f"Unsupported drift metric: {metric_name}")
    rows = list(observations)
    changes_by_org: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        change = _metric_change(
            float(row.baseline_value),
            float(row.comparison_value),
            mode=config["change_mode"],
        )
        if change is not None and math.isfinite(change):
            changes_by_org[row.organization_key].append(change)
    organization_changes = sorted(
        median(values) for values in changes_by_org.values() if values
    )
    resolved_minimum = max(5, int(minimum_organizations))
    if len(organization_changes) < resolved_minimum:
        return {
            "status": "insufficient_sample",
            "sample_size": len(rows),
            "organization_count": len(organization_changes),
            "minimum_organizations": resolved_minimum,
        }
    center = float(median(organization_changes))
    direction = "up" if center > 0 else "down"
    same_direction = sum(
        1 for value in organization_changes if (value > 0) == (center > 0)
    )
    agreement = float(same_direction) / float(len(organization_changes))
    threshold = float(config["threshold"])
    detected = abs(center) >= threshold and agreement >= DEFAULT_AGREEMENT_RATIO
    return {
        "status": "signal_detected" if detected else "no_signal",
        "sample_size": len(rows),
        "organization_count": len(organization_changes),
        "direction": direction,
        "median_change": center,
        "confidence_low": _quantile(organization_changes, 0.20),
        "confidence_high": _quantile(organization_changes, 0.80),
        "agreement_ratio": agreement,
        "threshold": threshold,
    }


def list_drift_events(
    db: Session,
    *,
    status_filter: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    query = db.query(PerformanceDriftEvent)
    if status_filter:
        query = query.filter(PerformanceDriftEvent.status == status_filter)
    rows = query.order_by(PerformanceDriftEvent.created_at.desc()).limit(limit).all()
    return {"items": [_event_payload(row) for row in rows], "returned": len(rows)}


def review_drift_event(
    db: Session,
    *,
    event_id: str,
    status: str,
    note: str,
    actor_user_id: str,
    audit_tenant_id: str,
) -> dict[str, Any]:
    if status not in REVIEW_STATUSES:
        raise ValueError("Unsupported drift review status.")
    resolved_note = note.strip()
    if not resolved_note:
        raise ValueError("An investigation note is required.")
    row = db.get(PerformanceDriftEvent, event_id)
    if row is None:
        raise ValueError("Performance drift event was not found.")
    reviewed_at = datetime.now(UTC)
    row.status = status
    row.investigation_note = resolved_note[:4000]
    row.reviewed_by_user_id = actor_user_id
    row.reviewed_at = reviewed_at
    row.updated_at = reviewed_at
    row.automatic_activation_allowed = False
    write_audit_log(
        db,
        tenant_id=audit_tenant_id,
        actor_user_id=actor_user_id,
        event_type="standards.performance_drift.reviewed",
        payload={
            "performance_drift_event_id": row.id,
            "status": status,
            "automatic_activation_allowed": False,
        },
    )
    db.commit()
    db.refresh(row)
    return _event_payload(row)


def _cohort_samples(
    rows: list[SearchConsoleDailyMetric],
    *,
    metric_name: str,
    contract_id: str,
    baseline_start: date,
    baseline_end: date,
    comparison_start: date,
    comparison_end: date,
    period_days: int,
    campaign_created: dict[str, date],
) -> tuple[dict[tuple[str, str], list[MinimizedDriftObservation]], int]:
    rows_by_sample: dict[tuple[str, str], list[SearchConsoleDailyMetric]] = defaultdict(list)
    for row in rows:
        rows_by_sample[(row.organization_id, row.campaign_id)].append(row)

    result: dict[tuple[str, str], list[MinimizedDriftObservation]] = defaultdict(list)
    excluded = 0
    required_days = math.ceil(float(period_days) * DEFAULT_MINIMUM_COVERAGE)
    for (organization_id, campaign_id), sample_rows in rows_by_sample.items():
        versions = {
            str(dict(row.metric_contract_versions or {}).get(contract_id) or "")
            for row in sample_rows
        }
        if len(versions) != 1 or "" in versions or any(
            row.scope_key == "legacy" for row in sample_rows
        ):
            excluded += 1
            continue
        scope_hashes = {
            _stable_hash(
                {
                    "provider": "google_search_console",
                    "search_type": row.search_type,
                    "dimensions": list(row.dimensions or []),
                    "filters": dict(row.filters or {}),
                    "date_treatment": "two_equal_calendar_windows",
                    "metric": metric_name,
                }
            )
            for row in sample_rows
        }
        if len(scope_hashes) != 1:
            excluded += 1
            continue
        version = next(iter(versions))
        scope_hash = next(iter(scope_hashes))
        created_on = campaign_created.get(campaign_id)
        if created_on is None or created_on > baseline_start:
            excluded += 1
            continue
        baseline_rows = [
            row for row in sample_rows if baseline_start <= row.metric_date <= baseline_end
        ]
        comparison_rows = [
            row for row in sample_rows if comparison_start <= row.metric_date <= comparison_end
        ]
        if (
            len({row.metric_date for row in baseline_rows}) < required_days
            or len({row.metric_date for row in comparison_rows}) < required_days
        ):
            excluded += 1
            continue
        baseline_value = _window_value(baseline_rows, metric_name)
        comparison_value = _window_value(comparison_rows, metric_name)
        if baseline_value is None or comparison_value is None:
            excluded += 1
            continue
        if metric_name in {"clicks", "impressions"} and baseline_value <= 0:
            excluded += 1
            continue
        result[(version, scope_hash)].append(
            MinimizedDriftObservation(
                organization_key=organization_id,
                sample_key=campaign_id,
                baseline_value=baseline_value,
                comparison_value=comparison_value,
            )
        )
    return result, excluded


def _window_value(rows: list[SearchConsoleDailyMetric], metric_name: str) -> float | None:
    if not rows:
        return None
    if metric_name == "clicks":
        return float(sum(int(row.clicks or 0) for row in rows)) / float(len(rows))
    if metric_name == "impressions":
        return float(sum(int(row.impressions or 0) for row in rows)) / float(len(rows))
    if metric_name == "avg_position":
        weighted = [
            (float(row.avg_position), max(int(row.impressions or 0), 1))
            for row in rows
            if row.avg_position is not None
        ]
        if not weighted:
            return None
        return sum(value * weight for value, weight in weighted) / sum(
            weight for _value, weight in weighted
        )
    return None


def _metric_change(baseline: float, comparison: float, *, mode: str) -> float | None:
    if mode == "relative":
        if baseline <= 0:
            return None
        return (comparison - baseline) / baseline
    return comparison - baseline


def _search_status_confounders(
    db: Session, *, start: date, end: date
) -> list[dict[str, Any]]:
    start_at = datetime.combine(start, datetime.min.time(), tzinfo=UTC)
    end_at = datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=UTC)
    rows = (
        db.query(StandardsChangeCandidate)
        .filter(
            StandardsChangeCandidate.source_id == "google.search.status_incidents",
            StandardsChangeCandidate.change_type == "incident_or_status_change",
            StandardsChangeCandidate.created_at >= start_at,
            StandardsChangeCandidate.created_at < end_at,
        )
        .order_by(StandardsChangeCandidate.created_at.desc())
        .all()
    )
    return [
        {
            "code": "google_search_status_change",
            "message": "A Google Search status change overlaps the comparison period.",
            "change_candidate_id": row.id,
        }
        for row in rows
    ]


def _evidence_digest(
    observations: Iterable[MinimizedDriftObservation],
    metric_name: str,
    scope_hash: str,
) -> str:
    minimized = [
        _stable_hash(
            {
                "organization": row.organization_key,
                "sample": row.sample_key,
                "baseline": round(row.baseline_value, 8),
                "comparison": round(row.comparison_value, 8),
            }
        )
        for row in observations
    ]
    return _stable_hash(
        {"metric": metric_name, "scope": scope_hash, "samples": sorted(minimized)}
    )


def _plain_language_summary(
    config: dict[str, Any], direction: str, center: float, organization_count: int
) -> str:
    if config["change_mode"] == "relative":
        movement = f"{abs(center) * 100:.0f}%"
    else:
        movement = f"{abs(center):.1f} positions"
    if config.get("lower_is_better"):
        movement_copy = (
            f"increased by a median of {movement}, which is farther from the top"
            if direction == "up"
            else f"decreased by a median of {movement}, which is closer to the top"
        )
    else:
        movement_copy = f"moved {direction} by a median of {movement}"
    return (
        f"Across {organization_count} separate organizations, {config['display_name']} "
        f"{movement_copy} during the comparison period. "
        "This is a possible ecosystem change, not proof of a Google algorithm update. "
        "Review provider health, known incidents, and affected customers before acting."
    )


def _event_payload(row: PerformanceDriftEvent) -> dict[str, Any]:
    return {
        "id": row.id,
        "detector_version": row.detector_version,
        "label": row.label,
        "status": row.status,
        "provider_name": row.provider_name,
        "metric_family": row.metric_family,
        "metric_contract_id": row.metric_contract_id,
        "metric_contract_version": row.metric_contract_version,
        "baseline_start": row.baseline_start,
        "baseline_end": row.baseline_end,
        "comparison_start": row.comparison_start,
        "comparison_end": row.comparison_end,
        "sample_size": row.sample_size,
        "organization_count": row.organization_count,
        "excluded_sample_size": row.excluded_sample_size,
        "direction": row.direction,
        "median_change": row.median_change,
        "confidence_low": row.confidence_low,
        "confidence_high": row.confidence_high,
        "agreement_ratio": row.agreement_ratio,
        "cohort_rules": dict(row.cohort_rules or {}),
        "known_confounders": list(row.known_confounders or []),
        "affected_metric_families": list(row.affected_metric_families or []),
        "plain_language_summary": row.plain_language_summary,
        "investigation_note": row.investigation_note,
        "reviewed_by_user_id": row.reviewed_by_user_id,
        "reviewed_at": row.reviewed_at,
        "automatic_activation_allowed": False,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _period_payload(
    baseline_start: date,
    baseline_end: date,
    comparison_start: date,
    comparison_end: date,
) -> dict[str, date]:
    return {
        "baseline_start": baseline_start,
        "baseline_end": baseline_end,
        "comparison_start": comparison_start,
        "comparison_end": comparison_end,
    }


def _empty_check(status: str, period_days: int, minimum: int) -> dict[str, Any]:
    return {
        "status": status,
        "checked_at": datetime.now(UTC),
        "detector_version": DETECTOR_VERSION,
        "period_days": period_days,
        "minimum_organizations": minimum,
        "events": [],
        "results": [],
        "known_confounders": [],
        "automatic_activation_allowed": False,
    }


def _quantile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return float(values[0])
    position = (len(values) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(values[lower])
    weight = position - lower
    return float(values[lower] * (1.0 - weight) + values[upper] * weight)


def _stable_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(encoded.encode("utf-8")).hexdigest()

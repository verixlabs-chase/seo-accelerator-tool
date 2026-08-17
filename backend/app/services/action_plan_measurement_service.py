from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.intelligence.lexicon import get_active_lexicon
from app.models.action_plan import ActionPlanMeasurement, ActionPlanOccurrence, ActionPlanStep
from app.models.authority import AuthorityLinkChange, AuthorityLinkGap
from app.models.campaign import Campaign
from app.models.content import ContentAsset
from app.models.crawl import CrawlPageResult, CrawlRun, TechnicalIssue
from app.models.google_business_profile import GoogleBusinessProfileDailyMetric
from app.models.intelligence import StrategyRecommendation
from app.models.local import ReviewVelocitySnapshot
from app.models.search_console_daily_metric import SearchConsoleDailyMetric
from app.models.website_performance import WebsitePerformanceMeasurement
from app.services import action_plan_forecast_service, metric_contract_service
from app.services.wordpress_regression_monitor_service import (
    evaluate_wordpress_regression_pause,
)


_DEFAULT_DIRECTIONS = {
    "organic.avg_position": "lower_is_better",
    "local.avg_rating": "higher_is_better",
    "local.gbp.total_appearances": "higher_is_better",
    "local.gbp.website_clicks": "higher_is_better",
    "local.gbp.call_clicks": "higher_is_better",
    "local.gbp.direction_requests": "higher_is_better",
    "local.gbp.bookings": "higher_is_better",
    "technical.issue_density": "lower_is_better",
    "technical.crawl_health": "higher_is_better",
    "authority.referring_page_link_present": "higher_is_better",
}
_GBP_METRIC_NAMES = {
    "local.gbp.total_appearances": (
        "BUSINESS_IMPRESSIONS_DESKTOP_MAPS",
        "BUSINESS_IMPRESSIONS_DESKTOP_SEARCH",
        "BUSINESS_IMPRESSIONS_MOBILE_MAPS",
        "BUSINESS_IMPRESSIONS_MOBILE_SEARCH",
    ),
    "local.gbp.website_clicks": ("WEBSITE_CLICKS",),
    "local.gbp.call_clicks": ("CALL_CLICKS",),
    "local.gbp.direction_requests": ("BUSINESS_DIRECTION_REQUESTS",),
    "local.gbp.bookings": ("BUSINESS_BOOKINGS",),
}
_MEASUREMENT_CONTRACT_VERSION = "2.0"
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


def _recommendation_evidence_payload(recommendation: StrategyRecommendation) -> dict[str, Any]:
    try:
        payload = json.loads(recommendation.evidence_json or "{}")
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _parse_evidence(recommendation: StrategyRecommendation) -> tuple[list[str], list[str]]:
    payload = _recommendation_evidence_payload(recommendation)
    evidence: list[str] = []
    affected_urls: list[str] = []
    if payload:
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
    contract = metric_contract_service.contract_for_lexicon_metric(metric.metric_id)
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
        "source_provider": None,
        "freshness_days": int(metric.freshness_days),
        "metric_contract_id": contract.contract_id if contract is not None else None,
        "metric_contract_version": contract.version if contract is not None else None,
        "metric_contract_status": contract.collection_status if contract is not None else None,
        "metric_contract_comparison_keys": (
            list(contract.comparison_keys) if contract is not None else []
        ),
        "scope_key": None,
        "entity_scope": {},
        "measurement_window_days": None,
        "insufficient_reason": "No matching measurement is available yet.",
    }


def _metric_target(metric: Any) -> dict[str, Any]:
    thresholds = metric.thresholds
    if thresholds is None:
        return {
            "direction": _DEFAULT_DIRECTIONS.get(metric.metric_id),
            "target_value": None,
            "target_range": None,
        }
    direction = str(thresholds.direction)
    good_boundary = thresholds.good_boundary
    return {
        "direction": direction,
        "target_value": float(good_boundary) if good_boundary is not None else None,
        "target_range": {
            "good_boundary": float(good_boundary) if good_boundary is not None else None,
            "poor_boundary": (
                float(thresholds.poor_boundary) if thresholds.poor_boundary is not None else None
            ),
            "semantics": thresholds.boundary_semantics,
        },
    }


def _measurement_track(*, action_category: str, metric_id: str | None) -> str:
    if action_category in {"local", "reputation", "google_business_profile"}:
        return "google_business_profile"
    if str(metric_id or "").startswith("local."):
        return "google_business_profile"
    return "website"


def _build_measurement_contract(
    *,
    occurrence: ActionPlanOccurrence,
    action: Any,
    primary_metric_definition: Any | None,
    metrics: list[dict[str, Any]],
    captured_at: datetime,
) -> dict[str, Any]:
    primary_metric_id = str(action.success_metric_ids[0]) if action.success_metric_ids else None
    primary_definition = (
        next(
            (item for item in metrics if item.get("metric_id") == primary_metric_id),
            None,
        )
        or {}
    )
    return {
        "version": _MEASUREMENT_CONTRACT_VERSION,
        "track": _measurement_track(
            action_category=str(action.category),
            metric_id=primary_metric_id,
        ),
        "primary_metric_id": primary_metric_id,
        "supporting_metric_ids": [str(item) for item in action.success_metric_ids[1:]],
        "provider": primary_definition.get("source_provider"),
        "entity_scope": dict(primary_definition.get("entity_scope") or {}),
        "baseline": {
            "captured_at": _iso(captured_at),
            "metric": dict(primary_definition),
        },
        "intervention": {
            "action_id": occurrence.action_id,
            "completed_at": None,
            "completion_proof_count": 0,
        },
        "observation": {
            "window_days": int(action.observation_window_days),
            "check_on_or_after": None,
        },
        "comparison": {
            "requires_same_metric_contract": True,
            "requires_same_provider": True,
            "requires_same_entity_scope": True,
            "requires_post_completion_data": True,
        },
        "target": (
            _metric_target(primary_metric_definition)
            if primary_metric_definition is not None
            else {}
        ),
        "result": {
            "classification": "waiting_for_results",
            "measured_at": None,
            "metric": None,
        },
    }


def _website_metric(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
    business_location_id: str | None,
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
            WebsitePerformanceMeasurement.organization_id == organization_id,
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
    contract = metric_contract_service.contract_for_lexicon_metric(metric.metric_id)
    if (
        row.scope_key == "legacy"
        or contract is None
        or dict(row.metric_contract_versions or {}).get(contract.contract_id) != contract.version
    ):
        payload["insufficient_reason"] = (
            "Fresh real-user website data is needed before this exact measurement can be compared."
        )
        return payload
    payload.update(
        {
            "status": "available",
            "value": float(getattr(row, column_name)),
            "source": "Chrome UX Report field data",
            "source_record_id": row.id,
            "measured_at": _iso(row.collection_end or row.captured_at),
            "evidence_window_start": _iso(row.collection_start),
            "evidence_window_end": _iso(row.collection_end),
            "scope": f"{row.scope}:{row.form_factor}",
            "source_provider": "chrome_ux_report",
            "entity_scope": {
                "organization_id": organization_id,
                "campaign_id": campaign_id,
                "business_location_id": business_location_id,
                "measured_url": row.measured_url,
                "scope": row.scope,
                "form_factor": row.form_factor,
            },
            "measurement_window_days": (
                (row.collection_end - row.collection_start).days + 1
                if row.collection_start and row.collection_end
                else None
            ),
            "insufficient_reason": None,
            "measured_url": row.measured_url,
            "metric_contract_id": contract.contract_id,
            "metric_contract_version": contract.version,
            "scope_key": row.scope_key,
        }
    )
    return payload


def _authority_link_presence_metric(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
    business_location_id: str | None,
    metric: Any,
    captured_at: datetime,
    evidence_payload: dict[str, Any],
) -> dict[str, Any]:
    payload = _metric_shell(metric)
    source_url = str(evidence_payload.get("source_url") or "").strip()
    measurement_contract = evidence_payload.get("measurement_contract")
    contract_payload = measurement_contract if isinstance(measurement_contract, dict) else {}
    owner_domain = str(contract_payload.get("owner_domain") or "").strip()
    if not source_url or not owner_domain:
        payload["insufficient_reason"] = (
            "The exact source page or business website is missing from this saved action."
        )
        return payload

    change = (
        db.query(AuthorityLinkChange)
        .filter(
            AuthorityLinkChange.tenant_id == tenant_id,
            AuthorityLinkChange.organization_id == organization_id,
            AuthorityLinkChange.campaign_id == campaign_id,
            AuthorityLinkChange.source_url == source_url,
            AuthorityLinkChange.observed_at <= captured_at,
        )
        .order_by(AuthorityLinkChange.observed_at.desc(), AuthorityLinkChange.created_at.desc())
        .first()
    )
    gap = (
        db.query(AuthorityLinkGap)
        .filter(
            AuthorityLinkGap.tenant_id == tenant_id,
            AuthorityLinkGap.organization_id == organization_id,
            AuthorityLinkGap.campaign_id == campaign_id,
            AuthorityLinkGap.source_url == source_url,
            AuthorityLinkGap.observed_at <= captured_at,
        )
        .order_by(AuthorityLinkGap.observed_at.desc(), AuthorityLinkGap.created_at.desc())
        .first()
    )
    observations: list[tuple[datetime, float, str, str]] = []
    if change is not None:
        observations.append(
            (
                _as_aware(change.observed_at) or change.observed_at,
                1.0 if change.change_state == "new" else 0.0,
                change.id,
                "New website mention" if change.change_state == "new" else "Lost website mention",
            )
        )
    if gap is not None:
        observations.append(
            (
                _as_aware(gap.observed_at) or gap.observed_at,
                0.0,
                gap.id,
                "Competitor-only page check",
            )
        )
    if not observations:
        payload["insufficient_reason"] = (
            "Run a fresh website-mention check for this exact page before measuring the result."
        )
        return payload

    observed_at, value, source_record_id, source_label = max(
        observations,
        key=lambda item: item[0],
    )
    contract = metric_contract_service.contract_for_lexicon_metric(metric.metric_id)
    scope = {
        "organization_id": organization_id,
        "campaign_id": campaign_id,
        "source_url": source_url,
        "owner_domain": owner_domain,
        "observed_at": observed_at,
    }
    contract_scope = (
        metric_contract_service.scope_evidence(contract.contract_id, scope, db=db)
        if contract is not None
        else {}
    )
    payload.update(
        {
            "status": "available",
            "value": value,
            "source": source_label,
            "source_provider": "market_research",
            "source_record_id": source_record_id,
            "measured_at": _iso(observed_at),
            "evidence_window_start": _iso(observed_at),
            "evidence_window_end": _iso(observed_at),
            "entity_scope": {
                "organization_id": organization_id,
                "campaign_id": campaign_id,
                "business_location_id": business_location_id,
                "source_url": source_url,
                "owner_domain": owner_domain,
            },
            "measurement_window_days": 1,
            "metric_contract_id": contract.contract_id if contract is not None else None,
            "metric_contract_version": contract.version if contract is not None else None,
            "scope_key": contract_scope.get("scope_key"),
            "insufficient_reason": None,
        }
    )
    return payload


def _search_metric(
    db: Session,
    *,
    organization_id: str,
    campaign_id: str,
    business_location_id: str | None,
    metric: Any,
    captured_at: datetime,
    observation_window_days: int,
) -> dict[str, Any]:
    payload = _metric_shell(metric)
    window_start = captured_at.date() - timedelta(days=max(observation_window_days - 1, 0))
    rows = (
        db.query(SearchConsoleDailyMetric)
        .filter(
            SearchConsoleDailyMetric.organization_id == organization_id,
            SearchConsoleDailyMetric.campaign_id == campaign_id,
            SearchConsoleDailyMetric.metric_date >= window_start,
            SearchConsoleDailyMetric.metric_date <= captured_at.date(),
        )
        .order_by(SearchConsoleDailyMetric.metric_date.asc())
        .all()
    )
    if not rows:
        return payload
    scope_keys = {str(row.scope_key or "") for row in rows}
    contract = metric_contract_service.contract_for_lexicon_metric(metric.metric_id)
    expected_version = contract.version if contract is not None else None
    if (
        len(scope_keys) != 1
        or "legacy" in scope_keys
        or any(
            dict(row.metric_contract_versions or {}).get(contract.contract_id) != expected_version
            for row in rows
            if contract is not None
        )
    ):
        payload["insufficient_reason"] = (
            "Fresh Search Console data is needed before this exact measurement can be compared."
        )
        return payload
    clicks = sum(int(row.clicks or 0) for row in rows)
    impressions = sum(int(row.impressions or 0) for row in rows)
    value: float | None = None
    if metric.metric_id == "organic.ctr" and impressions > 0:
        value = float(clicks) / float(impressions)
    elif metric.metric_id == "organic.impressions":
        value = float(impressions)
    elif metric.metric_id == "organic.avg_position":
        weighted_rows = [
            row for row in rows if row.avg_position is not None and int(row.impressions or 0) > 0
        ]
        weighted_impressions = sum(int(row.impressions or 0) for row in weighted_rows)
        if weighted_impressions > 0:
            value = sum(
                float(row.avg_position) * int(row.impressions or 0) for row in weighted_rows
            ) / float(weighted_impressions)
    if value is None:
        return payload
    first_date = rows[0].metric_date
    last_date = rows[-1].metric_date
    payload.update(
        {
            "status": "available",
            "value": value,
            "source": "Google Search Console",
            "source_provider": "google_search_console",
            "source_record_id": f"{rows[0].id}:{rows[-1].id}:{len(rows)}",
            "measured_at": _iso(last_date),
            "evidence_window_start": _iso(first_date),
            "evidence_window_end": _iso(last_date),
            "entity_scope": {
                "organization_id": organization_id,
                "campaign_id": campaign_id,
                "business_location_id": business_location_id,
                "property_uri": rows[-1].property_uri,
                "search_type": rows[-1].search_type,
                "dimensions": list(rows[-1].dimensions or []),
                "filters": dict(rows[-1].filters or {}),
            },
            "metric_contract_id": contract.contract_id if contract is not None else None,
            "metric_contract_version": expected_version,
            "scope_key": rows[-1].scope_key,
            "measurement_window_days": observation_window_days,
            "rows_measured": len(rows),
            "insufficient_reason": None,
        }
    )
    return payload


def _review_metric(
    db: Session,
    *,
    tenant_id: str,
    campaign_id: str,
    business_location_id: str | None,
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
    contract = metric_contract_service.contract_for_lexicon_metric(metric.metric_id)
    if (
        row.scope_key == "legacy"
        or contract is None
        or dict(row.metric_contract_versions or {}).get(contract.contract_id) != contract.version
    ):
        payload["insufficient_reason"] = (
            "Fresh review data is needed before this exact measurement can be compared."
        )
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
            "source_provider": "google_business_profile_reviews",
            "source_record_id": row.id,
            "measured_at": _iso(captured_at),
            "evidence_window_start": _iso(
                captured_at - timedelta(days=30) if captured_at else None
            ),
            "evidence_window_end": _iso(captured_at),
            "entity_scope": {
                "campaign_id": campaign_id,
                "business_location_id": business_location_id,
                "profile_id": row.profile_id,
            },
            "measurement_window_days": 30,
            "metric_contract_id": contract.contract_id,
            "metric_contract_version": contract.version,
            "scope_key": row.scope_key,
            "insufficient_reason": None,
        }
    )
    return payload


def _google_business_profile_metric(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
    business_location_id: str | None,
    metric: Any,
    captured_at: datetime,
    observation_window_days: int,
) -> dict[str, Any]:
    payload = _metric_shell(metric)
    if not business_location_id:
        payload["insufficient_reason"] = "Choose a business location before measuring this action."
        return payload
    metric_names = _GBP_METRIC_NAMES[metric.metric_id]
    window_start = captured_at.date() - timedelta(days=max(observation_window_days - 1, 0))
    rows = (
        db.query(GoogleBusinessProfileDailyMetric)
        .filter(
            GoogleBusinessProfileDailyMetric.tenant_id == tenant_id,
            GoogleBusinessProfileDailyMetric.organization_id == organization_id,
            GoogleBusinessProfileDailyMetric.campaign_id == campaign_id,
            GoogleBusinessProfileDailyMetric.business_location_id == business_location_id,
            GoogleBusinessProfileDailyMetric.metric_name.in_(metric_names),
            GoogleBusinessProfileDailyMetric.metric_date >= window_start,
            GoogleBusinessProfileDailyMetric.metric_date <= captured_at.date(),
            GoogleBusinessProfileDailyMetric.metric_value.isnot(None),
        )
        .order_by(GoogleBusinessProfileDailyMetric.metric_date.asc())
        .all()
    )
    if not rows:
        payload["insufficient_reason"] = (
            "Google Business Profile results have not been collected for this location yet."
        )
        return payload
    contract = metric_contract_service.contract_for_lexicon_metric(metric.metric_id)
    scope_keys = {str(row.scope_key or "") for row in rows}
    if len(scope_keys) != 1 or "legacy" in scope_keys or contract is None:
        payload["insufficient_reason"] = (
            "Fresh Google Business Profile data is needed before this exact measurement can be compared."
        )
        return payload
    payload.update(
        {
            "status": "available",
            "value": float(sum(int(row.metric_value or 0) for row in rows)),
            "source": "Connected Google Business Profile",
            "source_provider": "google_business_profile",
            "source_record_id": f"{rows[0].id}:{rows[-1].id}:{len(rows)}",
            "measured_at": _iso(rows[-1].metric_date),
            "evidence_window_start": _iso(rows[0].metric_date),
            "evidence_window_end": _iso(rows[-1].metric_date),
            "entity_scope": {
                "organization_id": organization_id,
                "campaign_id": campaign_id,
                "business_location_id": business_location_id,
                "connection_id": rows[-1].connection_id,
                "metric_names": list(metric_names),
                "external_resource_id": rows[-1].external_resource_id,
                "source_account_id": rows[-1].source_account_id,
            },
            "metric_contract_id": contract.contract_id,
            "metric_contract_version": contract.version,
            "scope_key": rows[-1].scope_key,
            "measurement_window_days": observation_window_days,
            "rows_measured": len(rows),
            "insufficient_reason": None,
        }
    )
    return payload


def _technical_issue_density(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
    business_location_id: str | None,
    metric: Any,
    captured_at: datetime,
) -> dict[str, Any]:
    payload = _metric_shell(metric)
    crawl = (
        db.query(CrawlRun)
        .filter(
            CrawlRun.tenant_id == tenant_id,
            CrawlRun.campaign_id == campaign_id,
            CrawlRun.status.in_(("complete", "completed")),
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
            "source_provider": "website_crawl",
            "source_record_id": crawl.id,
            "measured_at": _iso(measured_at),
            "evidence_window_start": _iso(_as_aware(crawl.started_at or crawl.created_at)),
            "evidence_window_end": _iso(measured_at),
            "pages_checked": int(page_count),
            "issues_found": int(issue_count),
            "entity_scope": {
                "organization_id": organization_id,
                "campaign_id": campaign_id,
                "business_location_id": business_location_id,
                "crawl_scope": "campaign",
            },
            "measurement_window_days": 1,
            "metric_contract_id": "crawl.affected_page_ratio",
            "metric_contract_version": metric_contract_service.contract_definition(
                "crawl.affected_page_ratio", db=db
            ).version,
            "scope_key": metric_contract_service.scope_evidence(
                "crawl.affected_page_ratio",
                {
                    "organization_id": organization_id,
                    "campaign_id": campaign_id,
                    "crawl_run_id": crawl.id,
                    "crawl_scope": "campaign",
                    "captured_at": measured_at,
                    "pages_checked": int(page_count),
                },
                db=db,
            )["scope_key"],
            "insufficient_reason": None,
        }
    )
    return payload


def _content_growth(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
    business_location_id: str | None,
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
            "source_provider": "content_inventory",
            "source_record_id": None,
            "measured_at": _iso(captured_at),
            "evidence_window_start": _iso(previous_start),
            "evidence_window_end": _iso(captured_at),
            "current_30_day_count": int(current_count),
            "previous_30_day_count": int(previous_count),
            "entity_scope": {
                "organization_id": organization_id,
                "campaign_id": campaign_id,
                "business_location_id": business_location_id,
            },
            "measurement_window_days": 60,
            "insufficient_reason": None,
        }
    )
    return payload


def _capture_metric(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
    business_location_id: str | None,
    metric: Any,
    captured_at: datetime,
    observation_window_days: int,
    evidence_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if metric.metric_id in _WEBSITE_COLUMNS:
        return _website_metric(
            db,
            tenant_id=tenant_id,
            organization_id=organization_id,
            campaign_id=campaign_id,
            business_location_id=business_location_id,
            metric=metric,
            captured_at=captured_at,
        )
    if metric.metric_id in {"organic.ctr", "organic.impressions", "organic.avg_position"}:
        return _search_metric(
            db,
            organization_id=organization_id,
            campaign_id=campaign_id,
            business_location_id=business_location_id,
            metric=metric,
            captured_at=captured_at,
            observation_window_days=observation_window_days,
        )
    if metric.metric_id in {"local.review_velocity_30d", "local.avg_rating"}:
        return _review_metric(
            db,
            tenant_id=tenant_id,
            campaign_id=campaign_id,
            business_location_id=business_location_id,
            metric=metric,
            captured_at=captured_at,
        )
    if metric.metric_id in _GBP_METRIC_NAMES:
        return _google_business_profile_metric(
            db,
            tenant_id=tenant_id,
            organization_id=organization_id,
            campaign_id=campaign_id,
            business_location_id=business_location_id,
            metric=metric,
            captured_at=captured_at,
            observation_window_days=observation_window_days,
        )
    if metric.metric_id == "technical.issue_density":
        return _technical_issue_density(
            db,
            tenant_id=tenant_id,
            organization_id=organization_id,
            campaign_id=campaign_id,
            business_location_id=business_location_id,
            metric=metric,
            captured_at=captured_at,
        )
    if metric.metric_id == "content.growth_rate":
        return _content_growth(
            db,
            tenant_id=tenant_id,
            organization_id=organization_id,
            campaign_id=campaign_id,
            business_location_id=business_location_id,
            metric=metric,
            captured_at=captured_at,
        )
    if metric.metric_id == "authority.referring_page_link_present":
        return _authority_link_presence_metric(
            db,
            tenant_id=tenant_id,
            organization_id=organization_id,
            campaign_id=campaign_id,
            business_location_id=business_location_id,
            metric=metric,
            captured_at=captured_at,
            evidence_payload=evidence_payload or {},
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
                    parsed = datetime.combine(
                        date.fromisoformat(str(value)), datetime.min.time(), UTC
                    )
                except ValueError:
                    continue
            target.append(_as_aware(parsed) or parsed)
    return (min(starts) if starts else None, max(ends) if ends else None)


def capture_governed_metric_snapshot(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
    business_location_id: str | None,
    metric_id: str,
    observation_window_days: int,
    captured_at: datetime | None = None,
) -> dict[str, Any]:
    """Read one governed metric without creating work or changing an external system."""

    campaign = (
        db.query(Campaign)
        .filter(
            Campaign.id == campaign_id,
            Campaign.tenant_id == tenant_id,
            Campaign.organization_id == organization_id,
        )
        .first()
    )
    if campaign is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    if business_location_id and campaign.business_location_id != business_location_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The saved test location no longer matches this business",
        )
    lexicon = get_active_lexicon(db, tenant_id=tenant_id)
    metric = lexicon.metric_index.get(str(metric_id))
    if metric is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The saved measurement is no longer available in the active rules",
        )
    return _capture_metric(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=campaign_id,
        business_location_id=business_location_id,
        metric=metric,
        captured_at=captured_at or datetime.now(UTC),
        observation_window_days=observation_window_days,
    )


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

    evidence_payload = _recommendation_evidence_payload(recommendation)
    metrics = [
        _capture_metric(
            db,
            tenant_id=occurrence.tenant_id,
            organization_id=occurrence.organization_id,
            campaign_id=occurrence.campaign_id,
            business_location_id=occurrence.business_location_id,
            metric=lexicon.metric_index[metric_id],
            captured_at=resolved_at,
            observation_window_days=int(action.observation_window_days),
            evidence_payload=evidence_payload,
        )
        for metric_id in action.success_metric_ids
    ]
    evidence, affected_urls = _parse_evidence(recommendation)
    measured_urls = [str(item["measured_url"]) for item in metrics if item.get("measured_url")]
    window_start, window_end = _window_bounds(metrics)
    has_baseline = any(item.get("status") == "available" for item in metrics)
    primary_metric_definition = (
        lexicon.metric_index.get(str(action.success_metric_ids[0]))
        if action.success_metric_ids
        else None
    )
    measurement_contract = _build_measurement_contract(
        occurrence=occurrence,
        action=action,
        primary_metric_definition=primary_metric_definition,
        metrics=metrics,
        captured_at=resolved_at,
    )
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
        result_classification="waiting_for_results",
        measurement_contract=measurement_contract,
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
    measurement.result_classification = "waiting_for_results"
    measurement.outcome_metrics = []
    measurement.outcome_evidence = []
    measurement.outcome_measured_at = None
    contract = dict(measurement.measurement_contract or {})
    contract["intervention"] = {
        "action_id": measurement.action_id,
        "completed_at": _iso(completed_at),
        "completion_proof_count": len(measurement.completion_proof),
    }
    observation = dict(contract.get("observation") or {})
    observation["window_days"] = measurement.observation_window_days
    observation["check_on_or_after"] = _iso(measurement.observation_due_at)
    contract["observation"] = observation
    contract["result"] = {
        "classification": "waiting_for_results",
        "measured_at": None,
        "metric": None,
    }
    measurement.measurement_contract = contract
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
    measurement.result_classification = "waiting_for_results"
    contract = dict(measurement.measurement_contract or {})
    contract["intervention"] = {
        "action_id": measurement.action_id,
        "completed_at": None,
        "completion_proof_count": 0,
    }
    observation = dict(contract.get("observation") or {})
    observation["check_on_or_after"] = None
    contract["observation"] = observation
    contract["result"] = {
        "classification": "waiting_for_results",
        "measured_at": None,
        "metric": None,
    }
    measurement.measurement_contract = contract
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
        observed_at is not None and completed_at is not None and observed_at <= completed_at
    )
    scope_fields = (
        "metric_contract_id",
        "metric_contract_version",
        "scope_key",
        "source_provider",
        "aggregation",
        "scope",
        "measurement_window_days",
        "entity_scope",
    )
    scope_mismatches = [key for key in scope_fields if baseline.get(key) != observed.get(key)]
    insufficient_reasons: list[str] = []
    if before is None:
        insufficient_reasons.append("The starting measurement was not available.")
    if after is None:
        insufficient_reasons.append(
            str(
                observed.get("insufficient_reason")
                or "A follow-up measurement is not available yet."
            )
        )
    if direction not in {"higher_is_better", "lower_is_better"}:
        insufficient_reasons.append(
            "The measurement does not have a governed improvement direction."
        )
    if same_source_record:
        insufficient_reasons.append(
            "The connected source has not published a newer measurement yet."
        )
    if not_newer_than_work:
        insufficient_reasons.append("The newest measurement predates the completed work.")
    if scope_mismatches:
        insufficient_reasons.append(
            "The follow-up measurement does not match the starting provider, location, page, or date window."
        )
    if (
        before is None
        or after is None
        or direction not in {"higher_is_better", "lower_is_better"}
        or same_source_record
        or not_newer_than_work
        or scope_mismatches
    ):
        result.update(
            {
                "baseline_value": before,
                "change": None,
                "comparison": "insufficient_data",
                "comparison_requirements_met": False,
                "insufficient_reasons": insufficient_reasons,
            }
        )
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
            "comparison_requirements_met": True,
            "insufficient_reasons": [],
        }
    )
    return result


def _classify_primary_result(
    outcome_metrics: list[dict[str, Any]],
    success_metric_ids: list[str],
) -> tuple[str, str, dict[str, Any] | None]:
    primary_metric_id = str(success_metric_ids[0]) if success_metric_ids else None
    primary_result = next(
        (item for item in outcome_metrics if item.get("metric_id") == primary_metric_id),
        None,
    )
    primary_comparison = (
        str(primary_result.get("comparison")) if primary_result is not None else "insufficient_data"
    )
    if primary_comparison == "improved":
        return "improved", "helped", primary_result
    if primary_comparison == "unchanged":
        return "about_the_same", "did_not_help", primary_result
    if primary_comparison == "worse":
        return "worse", "did_not_help", primary_result
    return "not_enough_information", "insufficient_data", primary_result


def _capture_action_plan_outcome_metrics(
    db: Session,
    *,
    measurement: ActionPlanMeasurement,
    measured_at: datetime,
) -> list[dict[str, Any]]:
    lexicon = get_active_lexicon(db, tenant_id=measurement.tenant_id)
    recommendation = db.get(StrategyRecommendation, measurement.recommendation_id)
    evidence_payload = (
        _recommendation_evidence_payload(recommendation) if recommendation is not None else {}
    )
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
            tenant_id=measurement.tenant_id,
            organization_id=measurement.organization_id,
            campaign_id=measurement.campaign_id,
            business_location_id=measurement.business_location_id,
            metric=metric,
            captured_at=measured_at,
            observation_window_days=measurement.observation_window_days,
            evidence_payload=evidence_payload,
        )
        outcome_metrics.append(
            _comparison(
                baseline_by_id.get(str(metric_id), {}),
                observed,
                work_completed_at=measurement.work_completed_at,
            )
        )
    return outcome_metrics


def preview_action_plan_outcome(
    db: Session,
    *,
    measurement: ActionPlanMeasurement,
    measured_at: datetime | None = None,
) -> dict[str, Any]:
    """Inspect result readiness without completing or classifying the action plan."""
    resolved_at = measured_at or datetime.now(UTC)
    outcome_metrics = _capture_action_plan_outcome_metrics(
        db,
        measurement=measurement,
        measured_at=resolved_at,
    )
    result_classification, outcome_status, primary_result = _classify_primary_result(
        outcome_metrics,
        [str(item) for item in measurement.success_metric_ids or []],
    )
    primary_metric_id = (
        str((measurement.success_metric_ids or [""])[0]).strip() or None
    )
    primary_baseline = next(
        (
            item
            for item in measurement.baseline_metrics or []
            if str(item.get("metric_id") or "") == primary_metric_id
        ),
        None,
    )
    primary_baseline_ready = bool(
        primary_baseline is not None
        and primary_baseline.get("status") == "available"
        and primary_baseline.get("value") is not None
    )
    primary_ready = bool(
        primary_result is not None
        and primary_result.get("comparison") != "insufficient_data"
    )
    return {
        "measurement_id": measurement.id,
        "measured_at": resolved_at.isoformat(),
        "primary_metric_id": primary_metric_id,
        "primary_baseline_ready": primary_baseline_ready,
        "primary_metric_ready": primary_ready,
        "result_classification": result_classification,
        "outcome_status": outcome_status,
        "primary_result": dict(primary_result) if primary_result is not None else None,
        "outcome_metrics": outcome_metrics,
    }


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

    outcome_metrics = _capture_action_plan_outcome_metrics(
        db,
        measurement=measurement,
        measured_at=resolved_at,
    )

    result_classification, outcome_status, primary_result = _classify_primary_result(
        outcome_metrics,
        [str(item) for item in measurement.success_metric_ids or []],
    )

    measurement.measurement_status = "measured"
    measurement.outcome_status = outcome_status
    measurement.result_classification = result_classification
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
    contract = dict(measurement.measurement_contract or {})
    contract["result"] = {
        "classification": result_classification,
        "measured_at": _iso(resolved_at),
        "metric": dict(primary_result) if primary_result is not None else None,
    }
    measurement.measurement_contract = contract
    measurement.updated_at = resolved_at
    db.flush()
    managed_wordpress_safety = evaluate_wordpress_regression_pause(
        db,
        measurement=measurement,
    )
    contract = dict(measurement.measurement_contract or {})
    contract["managed_wordpress_safety"] = managed_wordpress_safety
    measurement.measurement_contract = contract
    forecast = action_plan_forecast_service.get_action_plan_forecast(
        db,
        occurrence_id=occurrence_id,
    )
    if forecast is not None:
        action_plan_forecast_service.compare_forecast_to_outcome(
            db,
            forecast=forecast,
            measurement=measurement,
            compared_at=resolved_at,
        )
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
        "result_classification": measurement.result_classification,
        "measurement_contract": dict(measurement.measurement_contract or {}),
        "measurement_track": (measurement.measurement_contract or {}).get("track", "website"),
        "primary_metric_id": (measurement.measurement_contract or {}).get("primary_metric_id"),
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

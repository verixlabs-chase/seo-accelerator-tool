from __future__ import annotations

import json
import re
from datetime import UTC, date, datetime, timedelta
from hashlib import sha256
from html import escape
from statistics import fmean
from typing import Any, Iterable

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.action_plan import ActionPlanMeasurement, ActionPlanOccurrence
from app.models.business_location import BusinessLocation
from app.models.campaign import Campaign
from app.models.campaign_daily_metric import CampaignDailyMetric
from app.models.crawl import CrawlRun, TechnicalIssue
from app.models.intelligence import StrategyRecommendation
from app.models.local import ReviewVelocitySnapshot
from app.models.rank import RankingSnapshot
from app.services import intelligence_service
from app.services.strategy_engine.thresholds import version_id as strategy_threshold_version


REPORT_SNAPSHOT_VERSION = "rpt1-owner-v2"
REPORT_PERIOD_DAYS = 30


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _iso(value: date | datetime | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        resolved = _aware(value)
        return resolved.isoformat() if resolved else None
    return value.isoformat()


def _round(value: float | int | None, digits: int = 1) -> float | int | None:
    if value is None:
        return None
    return round(float(value), digits)


def _sum(rows: Iterable[CampaignDailyMetric], field: str) -> int | None:
    values = [getattr(row, field) for row in rows if getattr(row, field) is not None]
    return int(sum(values)) if values else None


def _mean(rows: Iterable[CampaignDailyMetric], field: str) -> float | None:
    values = [float(getattr(row, field)) for row in rows if getattr(row, field) is not None]
    return _round(fmean(values)) if values else None


def _weighted_position(rows: Iterable[CampaignDailyMetric]) -> float | None:
    pairs = [
        (float(row.avg_position), int(row.impressions or 0))
        for row in rows
        if row.avg_position is not None
    ]
    weighted = [(position, weight) for position, weight in pairs if weight > 0]
    if weighted:
        return _round(sum(position * weight for position, weight in weighted) / sum(weight for _, weight in weighted))
    return _round(fmean(position for position, _ in pairs)) if pairs else None


def _latest(rows: list[CampaignDailyMetric], field: str) -> float | int | None:
    for row in reversed(rows):
        value = getattr(row, field)
        if value is not None:
            return _round(value)
    return None


def _change(current: float | int | None, previous: float | int | None) -> tuple[float | None, str]:
    if current is None or previous is None:
        return None, "not_enough_information"
    delta = float(current) - float(previous)
    if abs(delta) < 0.0001:
        return 0.0, "steady"
    percent = None if float(previous) == 0 else round((delta / abs(float(previous))) * 100, 1)
    return percent, "up" if delta > 0 else "down"


def _metric(
    *,
    key: str,
    label: str,
    current: float | int | None,
    previous: float | int | None,
    good_direction: str,
    unit: str,
    explanation: str,
    source_label: str,
    source_system: str,
    current_coverage: dict[str, Any],
    comparison_coverage: dict[str, Any],
    last_updated: date | datetime | None,
) -> dict[str, Any]:
    change_percent, direction = _change(current, previous)
    if direction == "not_enough_information":
        result = "not_enough_information"
    elif direction == "steady":
        result = "about_the_same"
    elif direction == good_direction:
        result = "improved"
    else:
        result = "declined"
    return {
        "key": key,
        "label": label,
        "current": current,
        "previous": previous,
        "change_percent": change_percent,
        "direction": direction,
        "result": result,
        "unit": unit,
        "explanation": explanation,
        "source": {
            "label": source_label,
            "system": source_system,
            "last_updated": _iso(last_updated),
        },
        "coverage": {
            "current": current_coverage,
            "comparison": comparison_coverage,
        },
    }


def _coverage(
    rows: Iterable[Any],
    field: str,
    *,
    expected: int = REPORT_PERIOD_DAYS,
) -> dict[str, Any]:
    values = [getattr(row, field) for row in rows if getattr(row, field, None) is not None]
    observed = len(values)
    if observed == 0:
        state = "unavailable"
    elif observed >= expected:
        state = "complete"
    else:
        state = "partial"
    return {"state": state, "observed": observed, "expected": expected}


def _record_coverage(observed: int, expected: int = 1) -> dict[str, Any]:
    if observed <= 0:
        state = "unavailable"
    elif observed >= expected:
        state = "complete"
    else:
        state = "partial"
    return {"state": state, "observed": observed, "expected": expected}


def _canonical_text(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _dedupe_story_items(items: Iterable[dict[str, Any]], *, limit: int = 6) -> list[dict[str, Any]]:
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        key = _canonical_text(str(item.get("canonical_action_id") or item.get("title") or item.get("id") or ""))
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(item)
        if len(unique) >= limit:
            break
    return unique


def _latest_by_date(rows: Iterable[Any], field: str) -> Any | None:
    resolved = list(rows)
    if not resolved:
        return None
    return max(resolved, key=lambda item: _aware(getattr(item, field)) or datetime.min.replace(tzinfo=UTC))


def _latest_rank_values(rows: Iterable[RankingSnapshot]) -> list[RankingSnapshot]:
    latest: dict[str, RankingSnapshot] = {}
    for row in rows:
        existing = latest.get(row.keyword_id)
        if existing is None or (_aware(row.captured_at) or datetime.min.replace(tzinfo=UTC)) > (
            _aware(existing.captured_at) or datetime.min.replace(tzinfo=UTC)
        ):
            latest[row.keyword_id] = row
    return list(latest.values())


def _rank_average(rows: Iterable[RankingSnapshot]) -> float | None:
    values = [float(row.position) for row in _latest_rank_values(rows)]
    return _round(fmean(values)) if values else None


def _top_ten_count(rows: Iterable[RankingSnapshot]) -> int | None:
    values = _latest_rank_values(rows)
    return sum(row.position <= 10 for row in values) if values else None


def _rank_trend_points(rows: Iterable[RankingSnapshot]) -> list[dict[str, Any]]:
    by_date: dict[date, list[RankingSnapshot]] = {}
    for row in rows:
        captured = _aware(row.captured_at)
        if captured is None:
            continue
        by_date.setdefault(captured.date(), []).append(row)
    return [
        {
            "date": captured_date.isoformat(),
            "average_position": _rank_average(date_rows),
            "keywords_checked": len(_latest_rank_values(date_rows)),
            "top_10": _top_ten_count(date_rows),
        }
        for captured_date, date_rows in sorted(by_date.items())
    ]


def _recommendation_evidence(recommendation: StrategyRecommendation | None) -> list[str]:
    if recommendation is None:
        return []
    try:
        payload = json.loads(recommendation.evidence_json or "{}")
    except json.JSONDecodeError:
        return []
    candidates: list[Any] = []
    if isinstance(payload, list):
        candidates = payload
    elif isinstance(payload, dict):
        raw = payload.get("evidence")
        if isinstance(raw, list):
            candidates = raw
        elif isinstance(raw, dict):
            candidates = list(raw.values())
    return [str(item).strip() for item in candidates if str(item).strip()][:3]


def _story_value(value: float | int | None, unit: str) -> str:
    if value is None:
        return "not measured"
    if unit == "rating":
        return f"{float(value):.1f} out of 5"
    if unit == "position":
        return f"position {float(value):.1f}"
    if isinstance(value, float) and not value.is_integer():
        return f"{value:,.1f} {unit}".strip()
    return f"{float(value):,.0f} {unit}".strip()


def _metric_story_detail(item: dict[str, Any]) -> str:
    current = _story_value(item.get("current"), str(item.get("unit") or ""))
    previous = _story_value(item.get("previous"), str(item.get("unit") or ""))
    coverage = ((item.get("coverage") or {}).get("current") or {}).get("state")
    coverage_note = "" if coverage == "complete" else f" Data coverage is {coverage or 'unknown'}."
    return f"The current period measured {current}, compared with {previous} in the earlier period.{coverage_note}"


def _plain_label(value: str | None) -> str:
    normalized = str(value or "Saved action").replace("::", " ").replace("_", " ").replace("-", " ")
    return " ".join(normalized.split()).strip().capitalize()


def _human_date(value: date) -> str:
    return f"{value:%b} {value.day}"


def _plan_map(db: Session, tenant_id: str, recommendations: list[StrategyRecommendation]) -> dict[str, dict]:
    try:
        return intelligence_service.build_recommendation_action_plans(
            db,
            tenant_id=tenant_id,
            recommendations=recommendations,
        )
    except Exception:
        return {}


def _action_label(
    recommendation_id: str | None,
    action_id: str | None,
    plans: dict[str, dict],
    recommendations_by_id: dict[str, StrategyRecommendation],
) -> str:
    plan = plans.get(str(recommendation_id or "")) or {}
    if plan.get("display_name"):
        return str(plan["display_name"])
    recommendation = recommendations_by_id.get(str(recommendation_id or ""))
    if recommendation and recommendation.rationale:
        sentence = recommendation.rationale.strip().split(".", 1)[0]
        if sentence:
            return sentence[:140]
    return _plain_label(action_id)


def _snapshot_hash(snapshot: dict[str, Any]) -> str:
    hashable = dict(snapshot)
    hashable.pop("snapshot_hash", None)
    return sha256(json.dumps(hashable, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()


def build_report_snapshot(
    db: Session,
    *,
    tenant_id: str,
    campaign: Campaign,
    month_number: int,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    resolved_generated_at = _aware(generated_at) or datetime.now(UTC)
    metric_rows = (
        db.query(CampaignDailyMetric)
        .filter(CampaignDailyMetric.campaign_id == campaign.id)
        .order_by(CampaignDailyMetric.metric_date.asc())
        .all()
    )
    observed_end = metric_rows[-1].metric_date if metric_rows else resolved_generated_at.date()
    current_start = observed_end - timedelta(days=REPORT_PERIOD_DAYS - 1)
    previous_end = current_start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=REPORT_PERIOD_DAYS - 1)
    current_rows = [row for row in metric_rows if current_start <= row.metric_date <= observed_end]
    previous_rows = [row for row in metric_rows if previous_start <= row.metric_date <= previous_end]

    current_start_dt = datetime.combine(current_start, datetime.min.time(), tzinfo=UTC)
    current_end_dt = datetime.combine(observed_end + timedelta(days=1), datetime.min.time(), tzinfo=UTC)
    previous_start_dt = datetime.combine(previous_start, datetime.min.time(), tzinfo=UTC)
    previous_end_dt = datetime.combine(previous_end + timedelta(days=1), datetime.min.time(), tzinfo=UTC)

    crawl_runs = (
        db.query(CrawlRun)
        .filter(
            CrawlRun.tenant_id == tenant_id,
            CrawlRun.campaign_id == campaign.id,
            CrawlRun.status == "completed",
            CrawlRun.finished_at.isnot(None),
        )
        .order_by(CrawlRun.finished_at.asc(), CrawlRun.id.asc())
        .all()
    )
    current_crawls = [
        row
        for row in crawl_runs
        if current_start_dt <= (_aware(row.finished_at) or current_start_dt - timedelta(days=1)) < current_end_dt
    ]
    previous_crawls = [
        row
        for row in crawl_runs
        if previous_start_dt <= (_aware(row.finished_at) or previous_start_dt - timedelta(days=1)) < previous_end_dt
    ]
    latest_current_crawl = _latest_by_date(current_crawls, "finished_at")
    latest_previous_crawl = _latest_by_date(previous_crawls, "finished_at")
    crawl_issue_counts = {
        str(crawl_run_id): int(issue_count)
        for crawl_run_id, issue_count in (
            db.query(TechnicalIssue.crawl_run_id, func.count(TechnicalIssue.id))
            .filter(
                TechnicalIssue.tenant_id == tenant_id,
                TechnicalIssue.campaign_id == campaign.id,
                TechnicalIssue.crawl_run_id.in_([row.id for row in crawl_runs] or [""]),
            )
            .group_by(TechnicalIssue.crawl_run_id)
            .all()
        )
    }

    def crawl_issue_count(run: CrawlRun | None) -> int | None:
        if run is None:
            return None
        return crawl_issue_counts.get(run.id, 0)

    review_snapshots = (
        db.query(ReviewVelocitySnapshot)
        .filter(
            ReviewVelocitySnapshot.tenant_id == tenant_id,
            ReviewVelocitySnapshot.campaign_id == campaign.id,
            ReviewVelocitySnapshot.captured_at >= previous_start_dt,
            ReviewVelocitySnapshot.captured_at < current_end_dt,
        )
        .order_by(ReviewVelocitySnapshot.captured_at.asc(), ReviewVelocitySnapshot.id.asc())
        .all()
    )
    current_reviews = [
        row for row in review_snapshots if current_start_dt <= (_aware(row.captured_at) or previous_start_dt) < current_end_dt
    ]
    previous_reviews = [
        row for row in review_snapshots if previous_start_dt <= (_aware(row.captured_at) or previous_start_dt - timedelta(days=1)) < previous_end_dt
    ]
    latest_current_review = _latest_by_date(current_reviews, "captured_at")
    latest_previous_review = _latest_by_date(previous_reviews, "captured_at")

    rank_rows = (
        db.query(RankingSnapshot)
        .filter(
            RankingSnapshot.tenant_id == tenant_id,
            RankingSnapshot.campaign_id == campaign.id,
            RankingSnapshot.captured_at >= previous_start_dt,
            RankingSnapshot.captured_at < current_end_dt,
        )
        .order_by(RankingSnapshot.captured_at.asc(), RankingSnapshot.id.asc())
        .all()
    )
    current_rank_rows = [
        row for row in rank_rows if current_start_dt <= (_aware(row.captured_at) or previous_start_dt) < current_end_dt
    ]
    previous_rank_rows = [
        row for row in rank_rows if previous_start_dt <= (_aware(row.captured_at) or previous_start_dt - timedelta(days=1)) < previous_end_dt
    ]

    search_last_updated = max(
        (row.metric_date for row in current_rows if row.clicks is not None or row.impressions is not None),
        default=None,
    )

    metrics = [
        _metric(
            key="google_visits",
            label="Visits from Google",
            current=_sum(current_rows, "clicks"),
            previous=_sum(previous_rows, "clicks"),
            good_direction="up",
            unit="visits",
            explanation="How many people clicked from Google to the website.",
            source_label="Google Search Console",
            source_system="search_console",
            current_coverage=_coverage(current_rows, "clicks"),
            comparison_coverage=_coverage(previous_rows, "clicks"),
            last_updated=search_last_updated,
        ),
        _metric(
            key="google_appearances",
            label="Times shown on Google",
            current=_sum(current_rows, "impressions"),
            previous=_sum(previous_rows, "impressions"),
            good_direction="up",
            unit="appearances",
            explanation="How often the business appeared in Google search results.",
            source_label="Google Search Console",
            source_system="search_console",
            current_coverage=_coverage(current_rows, "impressions"),
            comparison_coverage=_coverage(previous_rows, "impressions"),
            last_updated=search_last_updated,
        ),
        _metric(
            key="average_google_position",
            label="Average Google position",
            current=_weighted_position(current_rows),
            previous=_weighted_position(previous_rows),
            good_direction="down",
            unit="position",
            explanation="A smaller position number means the business appeared closer to the top.",
            source_label="Google Search Console",
            source_system="search_console",
            current_coverage=_coverage(current_rows, "avg_position"),
            comparison_coverage=_coverage(previous_rows, "avg_position"),
            last_updated=search_last_updated,
        ),
        _metric(
            key="website_issues",
            label="Issues in the latest website scan",
            current=crawl_issue_count(latest_current_crawl),
            previous=crawl_issue_count(latest_previous_crawl),
            good_direction="down",
            unit="issues",
            explanation="Problems found in the most recent completed website scan in each period.",
            source_label="InsightOS website scan",
            source_system="website_crawl",
            current_coverage=_record_coverage(len(current_crawls)),
            comparison_coverage=_record_coverage(len(previous_crawls)),
            last_updated=latest_current_crawl.finished_at if latest_current_crawl else None,
        ),
        _metric(
            key="reviews_last_30d",
            label="Recent Google reviews",
            current=latest_current_review.reviews_last_30d if latest_current_review else None,
            previous=latest_previous_review.reviews_last_30d if latest_previous_review else None,
            good_direction="up",
            unit="reviews",
            explanation="The recent review pace recorded at the end of each period.",
            source_label="Google Business Profile",
            source_system="google_business_profile",
            current_coverage=_record_coverage(len(current_reviews)),
            comparison_coverage=_record_coverage(len(previous_reviews)),
            last_updated=latest_current_review.captured_at if latest_current_review else None,
        ),
        _metric(
            key="average_rating",
            label="Average Google rating",
            current=_round(latest_current_review.avg_rating_last_30d) if latest_current_review else None,
            previous=_round(latest_previous_review.avg_rating_last_30d) if latest_previous_review else None,
            good_direction="up",
            unit="rating",
            explanation="The average review rating recorded at the end of each period.",
            source_label="Google Business Profile",
            source_system="google_business_profile",
            current_coverage=_record_coverage(len(current_reviews)),
            comparison_coverage=_record_coverage(len(previous_reviews)),
            last_updated=latest_current_review.captured_at if latest_current_review else None,
        ),
        _metric(
            key="tracked_keyword_position",
            label="Average tracked keyword position",
            current=_rank_average(current_rank_rows),
            previous=_rank_average(previous_rank_rows),
            good_direction="down",
            unit="position",
            explanation="The latest saved map or organic position for each tracked search in this period.",
            source_label="InsightOS rank tracking",
            source_system="rank_tracking",
            current_coverage=_record_coverage(len(_latest_rank_values(current_rank_rows))),
            comparison_coverage=_record_coverage(len(_latest_rank_values(previous_rank_rows))),
            last_updated=max((row.captured_at for row in current_rank_rows), default=None),
        ),
        _metric(
            key="tracked_keywords_top_10",
            label="Tracked searches in the top 10",
            current=_top_ten_count(current_rank_rows),
            previous=_top_ten_count(previous_rank_rows),
            good_direction="up",
            unit="keywords",
            explanation="How many tracked searches were in positions 1 through 10 on their latest check.",
            source_label="InsightOS rank tracking",
            source_system="rank_tracking",
            current_coverage=_record_coverage(len(_latest_rank_values(current_rank_rows))),
            comparison_coverage=_record_coverage(len(_latest_rank_values(previous_rank_rows))),
            last_updated=max((row.captured_at for row in current_rank_rows), default=None),
        ),
        _metric(
            key="visibility_health",
            label="Visibility health score",
            current=_latest(current_rows, "intelligence_score"),
            previous=_latest(previous_rows, "intelligence_score"),
            good_direction="up",
            unit="score",
            explanation="A consistent summary of the location's saved search and website evidence.",
            source_label="InsightOS intelligence engine",
            source_system="intelligence_engine",
            current_coverage=_coverage(current_rows, "intelligence_score"),
            comparison_coverage=_coverage(previous_rows, "intelligence_score"),
            last_updated=max((row.metric_date for row in current_rows if row.intelligence_score is not None), default=None),
        ),
    ]

    trend_series = [
        {
            "key": "google_discovery",
            "title": "How people found the business on Google",
            "description": "Daily website visits and search appearances from Google Search Console. Gaps mean Google did not provide a saved value for that day.",
            "source_label": "Google Search Console",
            "points": [
                {
                    "date": row.metric_date.isoformat(),
                    "visits": row.clicks,
                    "appearances": row.impressions,
                    "average_position": _round(row.avg_position),
                }
                for row in current_rows
                if row.clicks is not None or row.impressions is not None or row.avg_position is not None
            ],
            "comparison_points": [
                {
                    "date": row.metric_date.isoformat(),
                    "visits": row.clicks,
                    "appearances": row.impressions,
                    "average_position": _round(row.avg_position),
                }
                for row in previous_rows
                if row.clicks is not None or row.impressions is not None or row.avg_position is not None
            ],
        },
        {
            "key": "tracked_rankings",
            "title": "Tracked search positions",
            "description": "The average saved position for the searches being tracked. A lower position number is better.",
            "source_label": "InsightOS rank tracking",
            "points": _rank_trend_points(current_rank_rows),
            "comparison_points": _rank_trend_points(previous_rank_rows),
        },
        {
            "key": "website_scans",
            "title": "Website scan issues",
            "description": "Issue totals from each completed website scan. A lower total is better.",
            "source_label": "InsightOS website scan",
            "points": [
                {
                    "date": (_aware(row.finished_at) or resolved_generated_at).date().isoformat(),
                    "issues": crawl_issue_count(row),
                }
                for row in current_crawls
            ],
            "comparison_points": [
                {
                    "date": (_aware(row.finished_at) or resolved_generated_at).date().isoformat(),
                    "issues": crawl_issue_count(row),
                }
                for row in previous_crawls
            ],
        },
        {
            "key": "review_growth",
            "title": "Review pace and rating",
            "description": "Saved 30-day review pace and average rating from the connected business profile.",
            "source_label": "Google Business Profile",
            "points": [
                {
                    "date": (_aware(row.captured_at) or resolved_generated_at).date().isoformat(),
                    "reviews": row.reviews_last_30d,
                    "rating": _round(row.avg_rating_last_30d),
                }
                for row in current_reviews
            ],
            "comparison_points": [
                {
                    "date": (_aware(row.captured_at) or resolved_generated_at).date().isoformat(),
                    "reviews": row.reviews_last_30d,
                    "rating": _round(row.avg_rating_last_30d),
                }
                for row in previous_reviews
            ],
        },
    ]

    recommendations = (
        db.query(StrategyRecommendation)
        .filter(
            StrategyRecommendation.tenant_id == tenant_id,
            StrategyRecommendation.campaign_id == campaign.id,
        )
        .order_by(StrategyRecommendation.created_at.desc())
        .all()
    )
    plans = _plan_map(db, tenant_id, recommendations)
    recommendations_by_id = {item.id: item for item in recommendations}
    period_end_dt = current_end_dt

    completed_rows = (
        db.query(ActionPlanOccurrence)
        .filter(
            ActionPlanOccurrence.tenant_id == tenant_id,
            ActionPlanOccurrence.campaign_id == campaign.id,
            ActionPlanOccurrence.completed_at.isnot(None),
            ActionPlanOccurrence.completed_at >= current_start_dt,
            ActionPlanOccurrence.completed_at < period_end_dt,
        )
        .order_by(ActionPlanOccurrence.completed_at.desc())
        .limit(12)
        .all()
    )
    completed_actions = _dedupe_story_items([
        {
            "id": row.id,
            "canonical_action_id": row.action_id,
            "title": _action_label(row.recommendation_id, row.action_id, plans, recommendations_by_id),
            "completed_at": _iso(row.completed_at),
            "result_state": "waiting_for_measurement" if row.status == "waiting_for_results" else "completed",
        }
        for row in completed_rows
    ], limit=12)

    measured_rows = (
        db.query(ActionPlanMeasurement)
        .filter(
            ActionPlanMeasurement.tenant_id == tenant_id,
            ActionPlanMeasurement.campaign_id == campaign.id,
            ActionPlanMeasurement.measurement_status == "measured",
            ActionPlanMeasurement.outcome_measured_at.isnot(None),
            ActionPlanMeasurement.outcome_measured_at >= current_start_dt,
            ActionPlanMeasurement.outcome_measured_at < period_end_dt,
        )
        .order_by(ActionPlanMeasurement.outcome_measured_at.desc())
        .limit(12)
        .all()
    )
    measured_outcomes = _dedupe_story_items([
        {
            "id": row.id,
            "canonical_action_id": row.action_id,
            "title": _action_label(row.recommendation_id, row.action_id, plans, recommendations_by_id),
            "result": row.result_classification,
            "measured_at": _iso(row.outcome_measured_at),
            "metric_ids": list(row.success_metric_ids or []),
        }
        for row in measured_rows
    ], limit=12)

    active_occurrences = (
        db.query(ActionPlanOccurrence)
        .filter(
            ActionPlanOccurrence.tenant_id == tenant_id,
            ActionPlanOccurrence.campaign_id == campaign.id,
            ActionPlanOccurrence.status.in_(("ready", "in_progress", "blocked")),
        )
        .order_by(ActionPlanOccurrence.due_at.asc(), ActionPlanOccurrence.created_at.asc())
        .limit(24)
        .all()
    )

    measurements_by_occurrence = {
        row.occurrence_id: row
        for row in (
            db.query(ActionPlanMeasurement)
            .filter(
                ActionPlanMeasurement.tenant_id == tenant_id,
                ActionPlanMeasurement.campaign_id == campaign.id,
                ActionPlanMeasurement.occurrence_id.in_([item.id for item in active_occurrences] or [""]),
            )
            .all()
        )
    }

    def priority_item(
        *,
        item_id: str,
        recommendation: StrategyRecommendation | None,
        plan: dict[str, Any],
        status: str,
        due_at: datetime | None,
        canonical_action_id: str,
        measurement: ActionPlanMeasurement | None = None,
    ) -> dict[str, Any]:
        success_metrics = list(plan.get("success_metrics") or [])
        primary_metric = success_metrics[0] if success_metrics else None
        baseline = None
        if measurement is not None:
            available = [
                metric
                for metric in list(measurement.baseline_metrics or [])
                if metric.get("status") == "available"
            ]
            baseline = available[0] if available else None
        observation_days = int(plan.get("observation_window_days") or 0) or None
        title = str(plan.get("display_name") or _action_label(
            recommendation.id if recommendation else None,
            canonical_action_id,
            plans,
            recommendations_by_id,
        ))
        rationale = str(
            plan.get("why_it_matters")
            or (recommendation.rationale if recommendation else "")
            or "This action is tied to the saved evidence for this location."
        )
        metric_label = str(
            (primary_metric or {}).get("display_name")
            or (baseline or {}).get("display_name")
            or _plain_label((plan.get("success_metric_ids") or [""])[0])
        )
        metric_explanation = str(
            (primary_metric or {}).get("plain_language")
            or "The same saved measurement will be checked again after the work is completed."
        )
        measurement_source = (baseline or {}).get("source")
        return {
            "id": item_id,
            "canonical_action_id": str(plan.get("action_id") or canonical_action_id),
            "title": title,
            "detail": rationale,
            "why_it_matters": rationale,
            "steps": [str(step) for step in list(plan.get("steps") or [])[:5]],
            "status": status,
            "due_at": _iso(due_at),
            "owner_role": plan.get("owner_role"),
            "effort": plan.get("effort"),
            "confidence": _round(recommendation.confidence_score if recommendation else None),
            "evidence": _recommendation_evidence(recommendation),
            "measurement": {
                "metric_id": (primary_metric or {}).get("metric_id") or (plan.get("success_metric_ids") or [None])[0],
                "label": metric_label,
                "explanation": metric_explanation,
                "unit": (primary_metric or {}).get("unit") or (baseline or {}).get("unit"),
                "baseline": baseline,
                "source": measurement_source,
                "status": measurement.measurement_status if measurement else "measure_first",
                "check_after_days": observation_days,
            },
        }

    next_priorities = _dedupe_story_items(
        [
            priority_item(
                item_id=row.id,
                recommendation=recommendations_by_id.get(row.recommendation_id),
                plan=plans.get(row.recommendation_id) or {},
                status=row.status,
                due_at=row.due_at,
                canonical_action_id=row.action_id,
                measurement=measurements_by_occurrence.get(row.id),
            )
            for row in active_occurrences
        ],
        limit=5,
    )
    if not next_priorities:
        next_priorities = _dedupe_story_items(
            [
                priority_item(
                    item_id=recommendation.id,
                    recommendation=recommendation,
                    plan=plans.get(recommendation.id) or {},
                    status=str(getattr(recommendation.status, "value", recommendation.status)).lower(),
                    due_at=None,
                    canonical_action_id=str(
                        (plans.get(recommendation.id) or {}).get("action_id")
                        or recommendation.recommendation_type
                    ),
                )
                for recommendation in recommendations[:24]
            ],
            limit=5,
        )

    wins = [
        {
            "metric_key": item["key"],
            "title": f"{item['label']} improved",
            "detail": _metric_story_detail(item),
            "source": item.get("source"),
        }
        for item in metrics
        if item["result"] == "improved"
    ]
    losses = [
        {
            "metric_key": item["key"],
            "title": f"{item['label']} moved the wrong way",
            "detail": _metric_story_detail(item),
            "source": item.get("source"),
        }
        for item in metrics
        if item["result"] == "declined"
    ]
    risks = list(losses)
    website_issues = next((item for item in metrics if item["key"] == "website_issues"), None)
    if (
        website_issues
        and float(website_issues.get("current") or 0) > 0
        and not any(item.get("metric_key") == "website_issues" for item in risks)
    ):
        risks.append(
            {
                "metric_key": "website_issues",
                "title": f"{int(float(website_issues['current']))} website issues still need attention",
                "detail": "Work through the highest-impact website issue first, then measure again.",
            }
        )

    location = db.get(BusinessLocation, campaign.business_location_id) if campaign.business_location_id else None
    location_name = location.name if location else campaign.name
    latest_source_dates: list[datetime] = []
    if search_last_updated:
        latest_source_dates.append(datetime.combine(search_last_updated, datetime.min.time(), tzinfo=UTC))
    if latest_current_crawl and latest_current_crawl.finished_at:
        latest_source_dates.append(_aware(latest_current_crawl.finished_at) or resolved_generated_at)
    if latest_current_review:
        latest_source_dates.append(_aware(latest_current_review.captured_at) or resolved_generated_at)
    if current_rank_rows:
        latest_source_dates.append(max(_aware(row.captured_at) or resolved_generated_at for row in current_rank_rows))
    intelligence_last_updated = max(
        (row.metric_date for row in current_rows if row.intelligence_score is not None),
        default=None,
    )
    if intelligence_last_updated:
        latest_source_dates.append(datetime.combine(intelligence_last_updated, datetime.min.time(), tzinfo=UTC))
    latest_metric_at = max(latest_source_dates, default=None)
    data_age_days = (
        (resolved_generated_at.date() - latest_metric_at.date()).days
        if latest_metric_at is not None
        else None
    )
    measured_metric_count = sum(1 for item in metrics if item["current"] is not None)
    if measured_metric_count == 0:
        data_state = "not_enough_information"
    elif data_age_days is not None and data_age_days > 3:
        data_state = "stale"
    else:
        data_state = "current"

    observed_count = measured_metric_count
    if observed_count == 0:
        headline = f"More information is needed for {location_name}"
        summary = "There is not enough dated information yet to compare this location with the previous period."
    elif wins and risks:
        headline = f"{location_name} made progress, with {len(risks)} item{'s' if len(risks) != 1 else ''} to watch"
        summary = f"This report found {len(wins)} positive change{'s' if len(wins) != 1 else ''} and {len(risks)} risk{'s' if len(risks) != 1 else ''} from {_human_date(current_start)} through {_human_date(observed_end)}."
    elif wins:
        headline = f"{location_name} moved in the right direction"
        summary = f"This report found {len(wins)} positive change{'s' if len(wins) != 1 else ''} and no measured declines in the available data."
    elif risks:
        headline = f"{location_name} has {len(risks)} item{'s' if len(risks) != 1 else ''} needing attention"
        summary = "Start with the first priority below, then measure the same numbers again after the observation window."
    else:
        headline = f"{location_name} held steady"
        summary = "The available measurements did not show a clear improvement or decline from the previous period."

    snapshot: dict[str, Any] = {
        "schema_version": REPORT_SNAPSHOT_VERSION,
        "snapshot_hash": "",
        "generated_at": resolved_generated_at.isoformat(),
        "audience": "owner",
        "month_number": month_number,
        "campaign": {
            "id": campaign.id,
            "name": campaign.name,
            "domain": campaign.domain,
            "business_location_id": campaign.business_location_id,
            "location_name": location_name,
            "organization_id": campaign.organization_id,
        },
        "period": {
            "days": REPORT_PERIOD_DAYS,
            "start": current_start.isoformat(),
            "end": observed_end.isoformat(),
            "comparison_start": previous_start.isoformat(),
            "comparison_end": previous_end.isoformat(),
        },
        "executive_summary": {"headline": headline, "summary": summary},
        "metrics": metrics,
        "trend_series": trend_series,
        "wins": wins[:6],
        "losses": losses[:6],
        "completed_actions": completed_actions,
        "measured_outcomes": measured_outcomes,
        "risks": risks[:6],
        "next_priorities": next_priorities,
        "source": {
            "freshness_state": data_state,
            "latest_metric_at": _iso(latest_metric_at),
            "data_age_days": data_age_days,
            "metric_inventory": [
                {
                    "metric_key": item["key"],
                    "source": item.get("source"),
                    "coverage": item.get("coverage"),
                }
                for item in metrics
            ],
            "normalization_versions": sorted({row.normalization_version for row in current_rows}),
            "lexicon_versions": sorted({row.lexicon_version for row in active_occurrences + completed_rows}),
            "strategy_version": strategy_threshold_version,
        },
        "appendix": {
            "current_daily_records": len(current_rows),
            "comparison_daily_records": len(previous_rows),
            "rank_snapshot_records": db.query(RankingSnapshot).filter(
                RankingSnapshot.tenant_id == tenant_id,
                RankingSnapshot.campaign_id == campaign.id,
            ).count(),
            "technical_issue_records": db.query(TechnicalIssue).filter(
                TechnicalIssue.tenant_id == tenant_id,
                TechnicalIssue.campaign_id == campaign.id,
            ).count(),
            "recommendation_records": len(recommendations),
            "completed_crawl_records": len(current_crawls),
            "review_snapshot_records": len(current_reviews),
            "current_rank_snapshot_records": len(current_rank_rows),
        },
    }
    # Keep the original summary keys while the product migrates to the RPT1 story contract.
    snapshot.update(
        {
            "rank_snapshots": snapshot["appendix"]["rank_snapshot_records"],
            "technical_issues": website_issues.get("current") if website_issues else None,
            "intelligence_score": next((item["current"] for item in metrics if item["key"] == "visibility_health"), None),
            "reviews_last_30d": next((item["current"] for item in metrics if item["key"] == "reviews_last_30d"), None),
            "avg_rating_last_30d": next((item["current"] for item in metrics if item["key"] == "average_rating"), None),
        }
    )
    snapshot["snapshot_hash"] = _snapshot_hash(snapshot)
    return snapshot


def validate_snapshot(snapshot: dict[str, Any]) -> bool:
    expected = str(snapshot.get("snapshot_hash") or "")
    return bool(expected) and expected == _snapshot_hash(snapshot)


def normalize_snapshot(payload: dict[str, Any], campaign_name: str) -> dict[str, Any]:
    if payload.get("schema_version") in {"rpt1-owner-v1", REPORT_SNAPSHOT_VERSION}:
        return payload
    legacy = dict(payload)
    return {
        **legacy,
        "schema_version": "legacy-summary-v1",
        "snapshot_hash": "",
        "campaign": {"name": campaign_name, "location_name": campaign_name},
        "period": {},
        "executive_summary": {
            "headline": f"{campaign_name} report",
            "summary": "This older report contains a basic metric summary and cannot be reproduced as an RPT1 evidence snapshot.",
        },
        "metrics": [
            {"label": "Ranking snapshots", "current": legacy.get("rank_snapshots"), "unit": "snapshots", "result": "not_enough_information"},
            {"label": "Website issues", "current": legacy.get("technical_issues"), "unit": "issues", "result": "not_enough_information"},
            {"label": "Visibility health score", "current": legacy.get("intelligence_score"), "unit": "score", "result": "not_enough_information"},
            {"label": "Recent reviews", "current": legacy.get("reviews_last_30d"), "unit": "reviews", "result": "not_enough_information"},
        ],
        "wins": [],
        "losses": [],
        "completed_actions": [],
        "measured_outcomes": [],
        "risks": [],
        "next_priorities": [],
        "source": {"freshness_state": "unknown"},
        "appendix": {},
    }


def _display_value(metric: dict[str, Any]) -> str:
    value = metric.get("current")
    if value is None:
        return "Not measured"
    unit = str(metric.get("unit") or "")
    if unit == "rating":
        return f"{float(value):.1f} / 5"
    if unit == "position":
        return f"#{float(value):.1f}"
    if isinstance(value, float) and not value.is_integer():
        return f"{value:,.1f}"
    return f"{float(value):,.0f}"


def _chart_svg(
    current_points: list[dict[str, Any]],
    comparison_points: list[dict[str, Any]],
    *,
    field: str,
    label: str,
    unit: str,
    lower_is_better: bool = False,
) -> str:
    width, height = 720, 210
    left, right, top, bottom = 48, 18, 24, 42
    plot_width = width - left - right
    plot_height = height - top - bottom

    def valid(points: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [point for point in points if point.get(field) is not None]

    current = valid(current_points)
    comparison = valid(comparison_points)
    values = [float(point[field]) for point in current + comparison]
    if not values:
        return "<p class='empty-chart'>No saved trend values are available for this measurement yet.</p>"
    minimum, maximum = min(values), max(values)
    if abs(maximum - minimum) < 0.0001:
        padding = max(abs(maximum) * 0.1, 1.0)
        minimum -= padding
        maximum += padding

    def coords(points: list[dict[str, Any]]) -> str:
        if not points:
            return ""
        denominator = max(len(points) - 1, 1)
        coordinates: list[str] = []
        for index, point in enumerate(points):
            value = float(point[field])
            vertical_ratio = (
                (value - minimum) / (maximum - minimum)
                if lower_is_better
                else (maximum - value) / (maximum - minimum)
            )
            coordinates.append(
                f"{left + (index / denominator) * plot_width:.1f},{top + vertical_ratio * plot_height:.1f}"
            )
        return " ".join(coordinates)

    current_coords = coords(current)
    comparison_coords = coords(comparison)
    current_start = str(current[0].get("date") or "") if current else ""
    current_end = str(current[-1].get("date") or "") if current else ""
    unit_label = f" {unit}" if unit and unit not in {"position", "rating"} else ""
    comparison_line = (
        f"<polyline points='{comparison_coords}' fill='none' stroke='#8aa5bb' stroke-width='2' stroke-dasharray='7 6' opacity='.9'/>"
        if comparison_coords
        else ""
    )
    current_line = (
        f"<polyline points='{current_coords}' fill='none' stroke='#e85d19' stroke-width='3' stroke-linecap='round' stroke-linejoin='round'/>"
        if current_coords
        else ""
    )
    top_value = minimum if lower_is_better else maximum
    bottom_value = maximum if lower_is_better else minimum
    better_note = " Higher on the chart is better." if lower_is_better else ""
    return f"""
      <div class='chart-heading'><strong>{escape(label)}</strong><span>Orange: current period · Dashed: earlier period</span></div>
      <svg class='trend-chart' viewBox='0 0 {width} {height}' role='img' aria-label='{escape(label)} trend'>
        <line x1='{left}' y1='{top}' x2='{left}' y2='{top + plot_height}' stroke='#d7d7d2'/>
        <line x1='{left}' y1='{top + plot_height}' x2='{left + plot_width}' y2='{top + plot_height}' stroke='#d7d7d2'/>
        <line x1='{left}' y1='{top + plot_height / 2:.1f}' x2='{left + plot_width}' y2='{top + plot_height / 2:.1f}' stroke='#ecece8'/>
        <text x='4' y='{top + 5}' font-size='11' fill='#666'>{top_value:,.1f}{escape(unit_label)}</text>
        <text x='4' y='{top + plot_height + 4}' font-size='11' fill='#666'>{bottom_value:,.1f}{escape(unit_label)}</text>
        {comparison_line}{current_line}
        <text x='{left}' y='{height - 12}' font-size='11' fill='#666'>{escape(current_start)}</text>
        <text x='{left + plot_width}' y='{height - 12}' text-anchor='end' font-size='11' fill='#666'>{escape(current_end)}</text>
      </svg>
      <p class='chart-note'>{escape(better_note.strip())}</p>
    """


def _report_charts(snapshot: dict[str, Any]) -> str:
    series_by_key = {str(item.get("key")): item for item in snapshot.get("trend_series") or []}
    definitions = (
        ("google_discovery", "visits", "Visits from Google", "visits", False),
        ("google_discovery", "appearances", "Times shown on Google", "appearances", False),
        ("tracked_rankings", "average_position", "Average tracked keyword position", "position", True),
        ("website_scans", "issues", "Issues found in website scans", "issues", True),
        ("review_growth", "reviews", "Reviews received in the last 30 days", "reviews", False),
    )
    cards: list[str] = []
    for series_key, field, label, unit, lower_is_better in definitions:
        series = series_by_key.get(series_key) or {}
        current = list(series.get("points") or [])
        comparison = list(series.get("comparison_points") or [])
        if not any(point.get(field) is not None for point in current + comparison):
            continue
        cards.append(
            "<article class='chart-card'>"
            + _chart_svg(
                current,
                comparison,
                field=field,
                label=label,
                unit=unit,
                lower_is_better=lower_is_better,
            )
            + f"<p>{escape(str(series.get('description') or ''))}</p></article>"
        )
    if not cards:
        return "<section><h2>Performance over time</h2><p>No saved trend series are available yet. The report will add charts as connected measurements are collected.</p></section>"
    return "<section><h2>Performance over time</h2><p>These charts use the dated measurements frozen into this report.</p><div class='charts'>" + "".join(cards) + "</div></section>"


def _next_action_html(items: list[dict[str, Any]]) -> str:
    if not items:
        return "<section><h2>What to do next</h2><p>No verified next action is ready yet.</p></section>"
    cards: list[str] = []
    for index, item in enumerate(items, start=1):
        measurement = item.get("measurement") or {}
        steps = "".join(f"<li>{escape(str(step))}</li>" for step in item.get("steps") or [])
        evidence = "".join(f"<li>{escape(str(value))}</li>" for value in item.get("evidence") or [])
        check_after = measurement.get("check_after_days")
        check_label = (
            f"Check {escape(str(measurement.get('label') or 'the saved measurement'))} again after {int(check_after)} days."
            if check_after
            else f"Measure {escape(str(measurement.get('label') or 'the saved result'))} before and after the work."
        )
        cards.append(
            f"<article class='action-card'><div class='action-number'>{index}</div><div>"
            f"<h3>{escape(str(item.get('title') or 'Saved action'))}</h3>"
            f"<p><strong>Why this matters:</strong> {escape(str(item.get('why_it_matters') or item.get('detail') or ''))}</p>"
            + (f"<ol>{steps}</ol>" if steps else "")
            + f"<p class='measurement'><strong>How results will be checked:</strong> {check_label} "
            f"{escape(str(measurement.get('explanation') or ''))}</p>"
            + (f"<details><summary>Evidence used</summary><ul>{evidence}</ul></details>" if evidence else "")
            + "</div></article>"
        )
    return "<section><h2>What to do next</h2><p>Each action appears once, is tied to this location, and names the measurement used to check the result.</p><div class='action-list'>" + "".join(cards) + "</div></section>"


def _data_sources_html(metrics: list[dict[str, Any]]) -> str:
    rows: list[str] = []
    for item in metrics:
        source = item.get("source") or {}
        coverage = (item.get("coverage") or {}).get("current") or {}
        observed = int(coverage.get("observed") or 0)
        expected = int(coverage.get("expected") or 0)
        coverage_label = str(coverage.get("state") or "unknown").replace("_", " ").capitalize()
        rows.append(
            "<tr>"
            f"<td><strong>{escape(str(item.get('label') or 'Measurement'))}</strong></td>"
            f"<td>{escape(str(source.get('label') or 'Saved InsightOS data'))}</td>"
            f"<td>{escape(str(source.get('last_updated') or 'Not available'))}</td>"
            f"<td>{escape(coverage_label)} ({observed} of {expected})</td>"
            "</tr>"
        )
    return "<section><h2>Where the numbers came from</h2><p>This makes partial or missing information visible instead of treating it as zero.</p><div class='table-wrap'><table><thead><tr><th>Measurement</th><th>Source</th><th>Last updated</th><th>Coverage</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table></div></section>"


def render_report_html(snapshot: dict[str, Any]) -> str:
    campaign = snapshot.get("campaign") or {}
    period = snapshot.get("period") or {}
    executive = snapshot.get("executive_summary") or {}
    metrics = snapshot.get("metrics") or []

    def comparison_label(item: dict[str, Any]) -> str:
        if item.get("change_percent") is None:
            return "No comparison yet"
        return f"{abs(float(item['change_percent'])):.1f}% {item.get('direction')} from the earlier period"

    metric_cards = "".join(
        f"<article class='metric {escape(str(item.get('result') or ''))}'>"
        f"<p>{escape(str(item.get('label') or 'Metric'))}</p>"
        f"<strong>{escape(_display_value(item))}</strong>"
        f"<small>{escape(comparison_label(item))}</small>"
        f"<small class='source'>{escape(str((item.get('source') or {}).get('label') or 'Saved data'))} · "
        f"{escape(str((((item.get('coverage') or {}).get('current') or {}).get('state') or 'unknown')).replace('_', ' '))} coverage</small>"
        "</article>"
        for item in metrics
    )

    def list_section(title: str, items: list[dict], empty: str, detail_key: str = "detail") -> str:
        rows = "".join(
            f"<li><strong>{escape(str(item.get('title') or 'Saved item'))}</strong>"
            f"<span>{escape(str(item.get(detail_key) or item.get('result') or ''))}</span></li>"
            for item in items
        )
        return f"<section><h2>{escape(title)}</h2><ul>{rows or f'<li>{escape(empty)}</li>'}</ul></section>"

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(str(campaign.get('location_name') or campaign.get('name') or 'Business'))} progress report</title>
  <style>
    :root {{ color-scheme: light; --ink:#171717; --muted:#666; --line:#dedede; --accent:#e85d19; --good:#08775b; --bad:#b42318; }}
    * {{ box-sizing:border-box; }} body {{ margin:0; background:#f5f5f3; color:var(--ink); font:15px/1.5 Arial,sans-serif; }}
    main {{ max-width:1040px; margin:0 auto; padding:48px 28px 72px; }} header {{ border-top:7px solid var(--accent); background:#fff; padding:34px; }}
    .eyebrow {{ color:var(--accent); font-size:12px; font-weight:700; letter-spacing:.14em; text-transform:uppercase; }}
    h1 {{ max-width:760px; margin:8px 0 10px; font-size:34px; line-height:1.12; }} h2 {{ margin:0 0 14px; font-size:20px; }}
    .lede {{ max-width:760px; color:#3f3f3f; font-size:17px; }} .meta {{ color:var(--muted); font-size:13px; }}
    .metrics {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:12px; margin:20px 0; }}
    .metric, section {{ border:1px solid var(--line); background:#fff; border-radius:8px; padding:20px; }}
    .metric p {{ min-height:42px; margin:0; color:var(--muted); }} .metric strong {{ display:block; font-size:28px; }} .metric small {{ display:block; color:var(--muted); }}
    .metric .source {{ margin-top:10px; padding-top:10px; border-top:1px solid var(--line); font-size:11px; }}
    .metric.improved {{ border-left:4px solid var(--good); }} .metric.declined {{ border-left:4px solid var(--bad); }}
    .grid {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; margin-top:16px; }} ul {{ margin:0; padding-left:20px; }} li {{ margin:9px 0; }} li span {{ display:block; color:var(--muted); }}
    .charts {{ display:grid; grid-template-columns:1fr 1fr; gap:14px; margin-top:16px; }} .chart-card {{ border:1px solid var(--line); border-radius:8px; padding:14px; }}
    .chart-heading {{ display:flex; justify-content:space-between; gap:12px; align-items:baseline; }} .chart-heading span {{ color:var(--muted); font-size:11px; }}
    .trend-chart {{ display:block; width:100%; height:auto; margin-top:8px; }} .chart-card>p,.empty-chart {{ color:var(--muted); font-size:12px; }}
    .action-list {{ display:grid; gap:12px; margin-top:16px; }} .action-card {{ display:grid; grid-template-columns:38px 1fr; gap:14px; border:1px solid var(--line); border-radius:8px; padding:18px; }}
    .action-number {{ display:flex; align-items:center; justify-content:center; width:34px; height:34px; border-radius:50%; background:var(--accent); color:#fff; font-weight:700; }}
    .action-card h3 {{ margin:2px 0 8px; }} .action-card p {{ margin:8px 0; }} .measurement {{ border-left:3px solid var(--good); padding:9px 12px; background:#f1f8f5; }}
    details {{ color:var(--muted); }} table {{ width:100%; border-collapse:collapse; margin-top:12px; }} th,td {{ border-bottom:1px solid var(--line); padding:9px; text-align:left; vertical-align:top; }} th {{ color:var(--muted); font-size:12px; }} .table-wrap {{ overflow-x:auto; }}
    footer {{ margin-top:20px; color:var(--muted); font-size:12px; }} @media(max-width:760px) {{ .metrics,.grid {{ grid-template-columns:1fr; }} }}
    @media(max-width:760px) {{ .charts {{ grid-template-columns:1fr; }} }}
    @media print {{ body {{ background:#fff; }} main {{ padding:0; }} section,.metric,header {{ break-inside:avoid; }} }}
  </style>
</head>
<body><main>
  <header>
    <div class="eyebrow">InsightOS progress report</div>
    <h1>{escape(str(executive.get('headline') or 'Business progress report'))}</h1>
    <p class="lede">{escape(str(executive.get('summary') or ''))}</p>
    <p class="meta">{escape(str(campaign.get('location_name') or campaign.get('name') or 'Business'))} · {escape(str(period.get('start') or ''))} to {escape(str(period.get('end') or ''))}</p>
  </header>
  <div class="metrics">{metric_cards}</div>
  {_report_charts(snapshot)}
  <div class="grid">
    {list_section('What improved', snapshot.get('wins') or [], 'No clear improvement was measured yet.')}
    {list_section('What needs attention', snapshot.get('risks') or [], 'No measured risk was found in the available information.')}
    {list_section('Work completed', snapshot.get('completed_actions') or [], 'No completed action was recorded in this period.', 'completed_at')}
    {list_section('Measured results', snapshot.get('measured_outcomes') or [], 'Completed work is still waiting for enough follow-up information.', 'result')}
  </div>
  {_next_action_html(snapshot.get('next_priorities') or [])}
  {_data_sources_html(metrics)}
  <footer>Snapshot {escape(str(snapshot.get('snapshot_hash') or 'legacy'))} · Data freshness: {escape(str((snapshot.get('source') or {}).get('freshness_state') or 'unknown'))}. Technical evidence is retained in the stored report snapshot.</footer>
</main></body></html>"""


def report_pdf_lines(snapshot: dict[str, Any]) -> list[str]:
    campaign = snapshot.get("campaign") or {}
    period = snapshot.get("period") or {}
    executive = snapshot.get("executive_summary") or {}
    lines = [
        "InsightOS progress report",
        str(executive.get("headline") or campaign.get("location_name") or "Business report"),
        str(executive.get("summary") or ""),
        f"Location: {campaign.get('location_name') or campaign.get('name') or 'Business'}",
        f"Period: {period.get('start') or 'unknown'} to {period.get('end') or 'unknown'}",
        "Key measurements",
    ]
    for metric in snapshot.get("metrics") or []:
        comparison = "no comparison" if metric.get("change_percent") is None else f"{abs(float(metric['change_percent'])):.1f}% {metric.get('direction')}"
        lines.append(f"{metric.get('label')}: {_display_value(metric)} ({comparison})")
        source = metric.get("source") or {}
        coverage = (metric.get("coverage") or {}).get("current") or {}
        lines.append(
            f"  Source: {source.get('label') or 'Saved data'}; updated {source.get('last_updated') or 'not available'}; "
            f"coverage {coverage.get('state') or 'unknown'} ({coverage.get('observed') or 0} of {coverage.get('expected') or 0})."
        )
    for title, key in (
        ("What improved", "wins"),
        ("What needs attention", "risks"),
        ("Work completed", "completed_actions"),
        ("Measured results", "measured_outcomes"),
    ):
        lines.append(title)
        items = snapshot.get(key) or []
        if not items:
            lines.append("No verified item recorded.")
        for item in items:
            lines.append(f"- {item.get('title') or 'Saved item'}: {item.get('detail') or item.get('result') or item.get('status') or ''}")
    lines.append("What to do next")
    priorities = snapshot.get("next_priorities") or []
    if not priorities:
        lines.append("No verified next action is ready yet.")
    for index, item in enumerate(priorities, start=1):
        lines.append(f"{index}. {item.get('title') or 'Saved action'}")
        lines.append(f"Why: {item.get('why_it_matters') or item.get('detail') or ''}")
        for step_index, step in enumerate(item.get("steps") or [], start=1):
            lines.append(f"   {step_index}) {step}")
        measurement = item.get("measurement") or {}
        check_after = measurement.get("check_after_days")
        lines.append(
            f"Measure: {measurement.get('label') or 'saved result'}"
            + (f" after {check_after} days" if check_after else " before and after the work")
            + "."
        )
        if item.get("evidence"):
            lines.append(f"Evidence: {'; '.join(str(value) for value in item['evidence'])}")
    lines.extend(
        [
            "Evidence appendix",
            f"Snapshot version: {snapshot.get('schema_version')}",
            f"Snapshot hash: {snapshot.get('snapshot_hash') or 'legacy'}",
            f"Data freshness: {(snapshot.get('source') or {}).get('freshness_state') or 'unknown'}",
            f"Latest metric: {(snapshot.get('source') or {}).get('latest_metric_at') or 'not available'}",
            f"Strategy version: {(snapshot.get('source') or {}).get('strategy_version') or 'unknown'}",
        ]
    )
    return [str(line)[:220] for line in lines if str(line).strip()]

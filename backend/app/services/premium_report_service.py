from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from hashlib import sha256
from html import escape
from statistics import fmean
from typing import Any, Iterable

from sqlalchemy.orm import Session

from app.models.action_plan import ActionPlanMeasurement, ActionPlanOccurrence
from app.models.business_location import BusinessLocation
from app.models.campaign import Campaign
from app.models.campaign_daily_metric import CampaignDailyMetric
from app.models.crawl import TechnicalIssue
from app.models.intelligence import StrategyRecommendation
from app.models.rank import RankingSnapshot
from app.services import intelligence_service
from app.services.strategy_engine.thresholds import version_id as strategy_threshold_version


REPORT_SNAPSHOT_VERSION = "rpt1-owner-v1"
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
    }


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

    metrics = [
        _metric(
            key="google_visits",
            label="Visits from Google",
            current=_sum(current_rows, "clicks"),
            previous=_sum(previous_rows, "clicks"),
            good_direction="up",
            unit="visits",
            explanation="How many people clicked from Google to the website.",
        ),
        _metric(
            key="google_appearances",
            label="Times shown on Google",
            current=_sum(current_rows, "impressions"),
            previous=_sum(previous_rows, "impressions"),
            good_direction="up",
            unit="appearances",
            explanation="How often the business appeared in Google search results.",
        ),
        _metric(
            key="average_google_position",
            label="Average Google position",
            current=_weighted_position(current_rows),
            previous=_weighted_position(previous_rows),
            good_direction="down",
            unit="position",
            explanation="A smaller position number means the business appeared closer to the top.",
        ),
        _metric(
            key="website_issues",
            label="Website issues found",
            current=_latest(current_rows, "technical_issue_count"),
            previous=_latest(previous_rows, "technical_issue_count"),
            good_direction="down",
            unit="issues",
            explanation="The latest number of website problems recorded in each period.",
        ),
        _metric(
            key="reviews_last_30d",
            label="Recent Google reviews",
            current=_latest(current_rows, "reviews_last_30d"),
            previous=_latest(previous_rows, "reviews_last_30d"),
            good_direction="up",
            unit="reviews",
            explanation="The recent review pace recorded at the end of each period.",
        ),
        _metric(
            key="average_rating",
            label="Average Google rating",
            current=_latest(current_rows, "avg_rating_last_30d"),
            previous=_latest(previous_rows, "avg_rating_last_30d"),
            good_direction="up",
            unit="rating",
            explanation="The average review rating recorded at the end of each period.",
        ),
        _metric(
            key="visibility_health",
            label="Visibility health score",
            current=_latest(current_rows, "intelligence_score"),
            previous=_latest(previous_rows, "intelligence_score"),
            good_direction="up",
            unit="score",
            explanation="A consistent summary of the location's saved search and website evidence.",
        ),
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
    current_start_dt = datetime.combine(current_start, datetime.min.time(), tzinfo=UTC)
    period_end_dt = datetime.combine(observed_end + timedelta(days=1), datetime.min.time(), tzinfo=UTC)

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
    completed_actions = [
        {
            "id": row.id,
            "title": _action_label(row.recommendation_id, row.action_id, plans, recommendations_by_id),
            "completed_at": _iso(row.completed_at),
            "result_state": "waiting_for_measurement" if row.status == "waiting_for_results" else "completed",
        }
        for row in completed_rows
    ]

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
    measured_outcomes = [
        {
            "id": row.id,
            "title": _action_label(row.recommendation_id, row.action_id, plans, recommendations_by_id),
            "result": row.result_classification,
            "measured_at": _iso(row.outcome_measured_at),
            "metric_ids": list(row.success_metric_ids or []),
        }
        for row in measured_rows
    ]

    active_occurrences = (
        db.query(ActionPlanOccurrence)
        .filter(
            ActionPlanOccurrence.tenant_id == tenant_id,
            ActionPlanOccurrence.campaign_id == campaign.id,
            ActionPlanOccurrence.status.in_(("ready", "in_progress", "blocked")),
        )
        .order_by(ActionPlanOccurrence.due_at.asc(), ActionPlanOccurrence.created_at.asc())
        .limit(3)
        .all()
    )
    next_priorities = [
        {
            "id": row.id,
            "title": _action_label(row.recommendation_id, row.action_id, plans, recommendations_by_id),
            "status": row.status,
            "due_at": _iso(row.due_at),
        }
        for row in active_occurrences
    ]
    if not next_priorities:
        for recommendation in recommendations[:3]:
            next_priorities.append(
                {
                    "id": recommendation.id,
                    "title": _action_label(recommendation.id, recommendation.recommendation_type, plans, recommendations_by_id),
                    "status": str(getattr(recommendation.status, "value", recommendation.status)).lower(),
                    "due_at": None,
                }
            )

    wins = [
        {
            "metric_key": item["key"],
            "title": f"{item['label']} improved",
            "detail": item["explanation"],
        }
        for item in metrics
        if item["result"] == "improved"
    ]
    losses = [
        {
            "metric_key": item["key"],
            "title": f"{item['label']} moved the wrong way",
            "detail": item["explanation"],
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
    latest_metric_at = datetime.combine(observed_end, datetime.min.time(), tzinfo=UTC) if metric_rows else None
    data_age_days = (resolved_generated_at.date() - observed_end).days if metric_rows else None
    if not current_rows:
        data_state = "not_enough_information"
    elif data_age_days is not None and data_age_days > 3:
        data_state = "stale"
    else:
        data_state = "current"

    observed_count = sum(1 for item in metrics if item["current"] is not None)
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
    if payload.get("schema_version") == REPORT_SNAPSHOT_VERSION:
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
    .metric p {{ min-height:42px; margin:0; color:var(--muted); }} .metric strong {{ display:block; font-size:28px; }} .metric small {{ color:var(--muted); }}
    .metric.improved {{ border-left:4px solid var(--good); }} .metric.declined {{ border-left:4px solid var(--bad); }}
    .grid {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; margin-top:16px; }} ul {{ margin:0; padding-left:20px; }} li {{ margin:9px 0; }} li span {{ display:block; color:var(--muted); }}
    footer {{ margin-top:20px; color:var(--muted); font-size:12px; }} @media(max-width:760px) {{ .metrics,.grid {{ grid-template-columns:1fr; }} }}
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
  <div class="grid">
    {list_section('What improved', snapshot.get('wins') or [], 'No clear improvement was measured yet.')}
    {list_section('What needs attention', snapshot.get('risks') or [], 'No measured risk was found in the available information.')}
    {list_section('Work completed', snapshot.get('completed_actions') or [], 'No completed action was recorded in this period.', 'completed_at')}
    {list_section('Measured results', snapshot.get('measured_outcomes') or [], 'Completed work is still waiting for enough follow-up information.', 'result')}
    {list_section('What to do next', snapshot.get('next_priorities') or [], 'No next action is ready yet.', 'status')}
  </div>
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
    for title, key in (
        ("What improved", "wins"),
        ("What needs attention", "risks"),
        ("Work completed", "completed_actions"),
        ("Measured results", "measured_outcomes"),
        ("What to do next", "next_priorities"),
    ):
        lines.append(title)
        items = snapshot.get(key) or []
        if not items:
            lines.append("No verified item recorded.")
        for item in items:
            lines.append(f"- {item.get('title') or 'Saved item'}: {item.get('detail') or item.get('result') or item.get('status') or ''}")
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

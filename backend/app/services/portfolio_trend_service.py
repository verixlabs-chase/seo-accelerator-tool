from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.models.campaign_daily_metric import CampaignDailyMetric


WINDOW_DAYS = 14
MINIMUM_REPORTING_DAYS = 7


def build_portfolio_trends(
    db: Session,
    *,
    organization_id: str,
    locations: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compare saved portfolio history using only locations present in both windows."""

    campaign_to_location = {
        campaign_id: str(item["location_id"])
        for item in locations
        for campaign_id in item.get("campaign_ids", [])
    }
    location_by_id = {str(item["location_id"]): item for item in locations}
    if not campaign_to_location:
        return _empty_trends(locations_excluded=len(locations))

    latest_date = (
        db.query(CampaignDailyMetric.metric_date)
        .filter(
            CampaignDailyMetric.organization_id == organization_id,
            CampaignDailyMetric.campaign_id.in_(campaign_to_location),
        )
        .order_by(CampaignDailyMetric.metric_date.desc())
        .limit(1)
        .scalar()
    )
    if latest_date is None:
        return _empty_trends(locations_excluded=len(locations))

    previous_start = latest_date - timedelta(days=(WINDOW_DAYS * 2) - 1)
    previous_end = latest_date - timedelta(days=WINDOW_DAYS)
    current_start = latest_date - timedelta(days=WINDOW_DAYS - 1)
    rows = (
        db.query(CampaignDailyMetric)
        .filter(
            CampaignDailyMetric.organization_id == organization_id,
            CampaignDailyMetric.campaign_id.in_(campaign_to_location),
            CampaignDailyMetric.metric_date >= previous_start,
            CampaignDailyMetric.metric_date <= latest_date,
        )
        .order_by(CampaignDailyMetric.metric_date.asc(), CampaignDailyMetric.id.asc())
        .all()
    )
    location_days = _location_day_rows(rows, campaign_to_location=campaign_to_location)
    current_rows = [row for row in location_days if current_start <= row["date"] <= latest_date]
    previous_rows = [
        row for row in location_days if previous_start <= row["date"] <= previous_end
    ]
    eligible_location_ids = _eligible_locations(current_rows, previous_rows)
    eligible_current = [
        row for row in current_rows if row["location_id"] in eligible_location_ids
    ]
    eligible_previous = [
        row for row in previous_rows if row["location_id"] in eligible_location_ids
    ]
    ready = bool(eligible_location_ids)

    return {
        "data_state": "ready" if ready else "collecting_history",
        "window_days": WINDOW_DAYS,
        "minimum_reporting_days": MINIMUM_REPORTING_DAYS,
        "date_from": current_start.isoformat(),
        "date_to": latest_date.isoformat(),
        "comparison_date_from": previous_start.isoformat(),
        "comparison_date_to": previous_end.isoformat(),
        "locations_compared": len(eligible_location_ids),
        "locations_excluded": max(0, len(locations) - len(eligible_location_ids)),
        "coverage_note": (
            f"Changes compare the same {len(eligible_location_ids)} location"
            f"{'s' if len(eligible_location_ids) != 1 else ''} with at least "
            f"{MINIMUM_REPORTING_DAYS} saved days in both periods."
            if ready
            else (
                f"At least {MINIMUM_REPORTING_DAYS} saved days are required in both "
                "periods before portfolio changes are shown."
            )
        ),
        "summary": _summary_metrics(eligible_current, eligible_previous) if ready else [],
        "points": _portfolio_points(location_days),
        "alerts": (
            _change_alerts(
                current_rows=eligible_current,
                previous_rows=eligible_previous,
                location_by_id=location_by_id,
            )
            if ready
            else []
        ),
    }


def _empty_trends(*, locations_excluded: int = 0) -> dict[str, Any]:
    return {
        "data_state": "no_history",
        "window_days": WINDOW_DAYS,
        "minimum_reporting_days": MINIMUM_REPORTING_DAYS,
        "date_from": None,
        "date_to": None,
        "comparison_date_from": None,
        "comparison_date_to": None,
        "locations_compared": 0,
        "locations_excluded": locations_excluded,
        "coverage_note": "Saved daily performance is needed before portfolio changes can be compared.",
        "summary": [],
        "points": [],
        "alerts": [],
    }


def _location_day_rows(
    rows: list[CampaignDailyMetric],
    *,
    campaign_to_location: dict[str, str],
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, date], list[CampaignDailyMetric]] = defaultdict(list)
    for row in rows:
        location_id = campaign_to_location.get(str(row.campaign_id))
        if location_id:
            grouped[(location_id, row.metric_date)].append(row)

    results: list[dict[str, Any]] = []
    for (location_id, metric_date), day_rows in grouped.items():
        positions = [row for row in day_rows if row.avg_position is not None]
        position_weight = sum(
            float(row.avg_position) * max(int(row.impressions or 0), 1)
            for row in positions
        )
        position_denominator = sum(max(int(row.impressions or 0), 1) for row in positions)
        ratings = [
            float(row.avg_rating_last_30d)
            for row in day_rows
            if row.avg_rating_last_30d is not None
        ]
        results.append(
            {
                "location_id": location_id,
                "date": metric_date,
                "clicks": sum(int(row.clicks or 0) for row in day_rows),
                "impressions": sum(int(row.impressions or 0) for row in day_rows),
                "avg_position": (
                    position_weight / position_denominator if position_denominator else None
                ),
                "technical_issue_count": sum(
                    int(row.technical_issue_count or 0) for row in day_rows
                ),
                "reviews_last_30d": sum(int(row.reviews_last_30d or 0) for row in day_rows),
                "avg_rating_last_30d": (
                    sum(ratings) / len(ratings) if ratings else None
                ),
            }
        )
    results.sort(key=lambda item: (item["date"], item["location_id"]))
    return results


def _eligible_locations(
    current_rows: list[dict[str, Any]],
    previous_rows: list[dict[str, Any]],
) -> set[str]:
    current_days: dict[str, set[date]] = defaultdict(set)
    previous_days: dict[str, set[date]] = defaultdict(set)
    for row in current_rows:
        current_days[str(row["location_id"])].add(row["date"])
    for row in previous_rows:
        previous_days[str(row["location_id"])].add(row["date"])
    return {
        location_id
        for location_id in current_days.keys() & previous_days.keys()
        if len(current_days[location_id]) >= MINIMUM_REPORTING_DAYS
        and len(previous_days[location_id]) >= MINIMUM_REPORTING_DAYS
    }


def _portfolio_points(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[date, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["date"]].append(row)
    points: list[dict[str, Any]] = []
    for metric_date in sorted(grouped):
        day_rows = grouped[metric_date]
        positions = [row for row in day_rows if row["avg_position"] is not None]
        position_weight = sum(
            float(row["avg_position"]) * max(int(row["impressions"]), 1)
            for row in positions
        )
        position_denominator = sum(max(int(row["impressions"]), 1) for row in positions)
        points.append(
            {
                "date": metric_date.isoformat(),
                "clicks": sum(int(row["clicks"]) for row in day_rows),
                "impressions": sum(int(row["impressions"]) for row in day_rows),
                "avg_position": (
                    round(position_weight / position_denominator, 2)
                    if position_denominator
                    else None
                ),
                "website_issues": sum(
                    int(row["technical_issue_count"]) for row in day_rows
                ),
                "locations_reporting": len({str(row["location_id"]) for row in day_rows}),
            }
        )
    return points


def _summary_metrics(
    current_rows: list[dict[str, Any]],
    previous_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    current = _window_summary(current_rows)
    previous = _window_summary(previous_rows)
    return [
        _summary_item(
            code="daily_clicks",
            label="Average daily Google visits",
            current=current["daily_clicks"],
            previous=previous["daily_clicks"],
            lower_is_better=False,
            unit="visits",
        ),
        _summary_item(
            code="daily_impressions",
            label="Average daily Google appearances",
            current=current["daily_impressions"],
            previous=previous["daily_impressions"],
            lower_is_better=False,
            unit="appearances",
        ),
        _summary_item(
            code="avg_position",
            label="Average Google position",
            current=current["avg_position"],
            previous=previous["avg_position"],
            lower_is_better=True,
            unit="position",
        ),
        _summary_item(
            code="website_issues",
            label="Website problems",
            current=current["website_issues"],
            previous=previous["website_issues"],
            lower_is_better=True,
            unit="problems",
        ),
    ]


def _window_summary(rows: list[dict[str, Any]]) -> dict[str, float | None]:
    by_location: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_location[str(row["location_id"])].append(row)
    daily_clicks = 0.0
    daily_impressions = 0.0
    latest_issues = 0
    position_weight = 0.0
    position_denominator = 0.0
    for location_rows in by_location.values():
        daily_clicks += sum(int(row["clicks"]) for row in location_rows) / len(location_rows)
        daily_impressions += sum(int(row["impressions"]) for row in location_rows) / len(
            location_rows
        )
        latest = max(location_rows, key=lambda item: item["date"])
        latest_issues += int(latest["technical_issue_count"])
        for row in location_rows:
            if row["avg_position"] is None:
                continue
            weight = max(int(row["impressions"]), 1)
            position_weight += float(row["avg_position"]) * weight
            position_denominator += weight
    return {
        "daily_clicks": round(daily_clicks, 1),
        "daily_impressions": round(daily_impressions, 1),
        "avg_position": (
            round(position_weight / position_denominator, 2)
            if position_denominator
            else None
        ),
        "website_issues": float(latest_issues),
    }


def _summary_item(
    *,
    code: str,
    label: str,
    current: float | None,
    previous: float | None,
    lower_is_better: bool,
    unit: str,
) -> dict[str, Any]:
    if current is None or previous is None:
        return {
            "code": code,
            "label": label,
            "current": current,
            "previous": previous,
            "change": None,
            "change_percent": None,
            "direction": "not_measured",
            "tone": "neutral",
            "unit": unit,
        }
    change = current - previous
    threshold = 0.1 if code == "avg_position" else 0.01
    if abs(change) < threshold:
        direction = "steady"
        tone = "neutral"
    else:
        improved = change < 0 if lower_is_better else change > 0
        direction = "improved" if improved else "declined"
        tone = "positive" if improved else "negative"
    return {
        "code": code,
        "label": label,
        "current": round(current, 1),
        "previous": round(previous, 1),
        "change": round(change, 1),
        "change_percent": _percent_change(current, previous),
        "direction": direction,
        "tone": tone,
        "unit": unit,
    }


def _change_alerts(
    *,
    current_rows: list[dict[str, Any]],
    previous_rows: list[dict[str, Any]],
    location_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    current_by_location: dict[str, list[dict[str, Any]]] = defaultdict(list)
    previous_by_location: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in current_rows:
        current_by_location[str(row["location_id"])].append(row)
    for row in previous_rows:
        previous_by_location[str(row["location_id"])].append(row)

    alerts: list[dict[str, Any]] = []
    for location_id in sorted(current_by_location):
        location = location_by_id[location_id]
        current = _location_window(current_by_location[location_id])
        previous = _location_window(previous_by_location[location_id])
        candidates = _location_alert_candidates(location, current=current, previous=previous)
        negative = [item for item in candidates if item["tone"] == "negative"]
        positive = [item for item in candidates if item["tone"] == "positive"]
        if negative:
            alerts.append(min(negative, key=lambda item: int(item["priority"])))
        elif positive:
            alerts.append(min(positive, key=lambda item: int(item["priority"])))
    alerts.sort(
        key=lambda item: (
            0 if item["tone"] == "negative" else 1,
            int(item["priority"]),
            str(item["location_name"]).lower(),
        )
    )
    for item in alerts:
        item.pop("priority", None)
    return alerts[:8]


def _location_window(rows: list[dict[str, Any]]) -> dict[str, Any]:
    latest = max(rows, key=lambda item: item["date"])
    position_rows = [row for row in rows if row["avg_position"] is not None]
    position_weight = sum(
        float(row["avg_position"]) * max(int(row["impressions"]), 1)
        for row in position_rows
    )
    position_denominator = sum(
        max(int(row["impressions"]), 1) for row in position_rows
    )
    return {
        "daily_clicks": sum(int(row["clicks"]) for row in rows) / len(rows),
        "avg_position": (
            position_weight / position_denominator if position_denominator else None
        ),
        "technical_issue_count": int(latest["technical_issue_count"]),
        "reviews_last_30d": int(latest["reviews_last_30d"]),
        "avg_rating_last_30d": latest["avg_rating_last_30d"],
    }


def _location_alert_candidates(
    location: dict[str, Any],
    *,
    current: dict[str, Any],
    previous: dict[str, Any],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    name = str(location["location_name"])
    campaign_id = location.get("campaign_id")
    current_position = current["avg_position"]
    previous_position = previous["avg_position"]
    if current_position is not None and previous_position is not None:
        position_change = float(current_position) - float(previous_position)
        if position_change >= 3 and float(current_position) > 10:
            candidates.append(
                _alert(
                    location=location,
                    code="search_position_declined",
                    tone="negative",
                    priority=1,
                    title=f"{name} slipped in Google results",
                    detail=(
                        f"Its average position moved from about #{float(previous_position):.1f} "
                        f"to #{float(current_position):.1f}."
                    ),
                    evidence_label="Average position change",
                    evidence_value=round(position_change, 1),
                    action_label="Review search rankings",
                    action_href="/rankings",
                    campaign_id=campaign_id,
                )
            )
        elif position_change <= -3 and float(current_position) <= 10:
            candidates.append(
                _alert(
                    location=location,
                    code="search_position_improved",
                    tone="positive",
                    priority=2,
                    title=f"{name} moved closer to the top",
                    detail=(
                        f"Its average position improved from about #{float(previous_position):.1f} "
                        f"to #{float(current_position):.1f}."
                    ),
                    evidence_label="Positions improved",
                    evidence_value=round(abs(position_change), 1),
                    action_label="See what is ranking",
                    action_href="/rankings",
                    campaign_id=campaign_id,
                )
            )

    previous_clicks = float(previous["daily_clicks"])
    current_clicks = float(current["daily_clicks"])
    click_change = _percent_change(current_clicks, previous_clicks)
    if click_change is not None and previous_clicks >= 5:
        if click_change <= -25:
            candidates.append(
                _alert(
                    location=location,
                    code="google_visits_declined",
                    tone="negative",
                    priority=2,
                    title=f"Google visits fell for {name}",
                    detail=f"Average daily visits are down {abs(click_change):.0f}% from the prior period.",
                    evidence_label="Visit change",
                    evidence_value=f"{click_change:.0f}%",
                    action_label="Review Google traffic",
                    action_href="/dashboard",
                    campaign_id=campaign_id,
                )
            )
        elif click_change >= 25:
            candidates.append(
                _alert(
                    location=location,
                    code="google_visits_improved",
                    tone="positive",
                    priority=3,
                    title=f"Google visits grew for {name}",
                    detail=f"Average daily visits are up {click_change:.0f}% from the prior period.",
                    evidence_label="Visit change",
                    evidence_value=f"+{click_change:.0f}%",
                    action_label="See the traffic change",
                    action_href="/dashboard",
                    campaign_id=campaign_id,
                )
            )

    issue_change = int(current["technical_issue_count"]) - int(
        previous["technical_issue_count"]
    )
    if issue_change >= 3:
        candidates.append(
            _alert(
                location=location,
                code="website_issues_increased",
                tone="negative",
                priority=0,
                title=f"New website problems appeared for {name}",
                detail=f"The latest saved check has {issue_change} more website problems.",
                evidence_label="New website problems",
                evidence_value=issue_change,
                action_label="Open website health",
                action_href="/site-health",
                campaign_id=campaign_id,
            )
        )
    elif issue_change <= -3:
        candidates.append(
            _alert(
                location=location,
                code="website_issues_reduced",
                tone="positive",
                priority=1,
                title=f"Website health improved for {name}",
                detail=f"The latest saved check has {abs(issue_change)} fewer website problems.",
                evidence_label="Problems removed",
                evidence_value=abs(issue_change),
                action_label="Review website health",
                action_href="/site-health",
                campaign_id=campaign_id,
            )
        )
    return candidates


def _alert(
    *,
    location: dict[str, Any],
    code: str,
    tone: str,
    priority: int,
    title: str,
    detail: str,
    evidence_label: str,
    evidence_value: Any,
    action_label: str,
    action_href: str,
    campaign_id: str | None,
) -> dict[str, Any]:
    return {
        "code": code,
        "tone": tone,
        "priority": priority,
        "location_id": location["location_id"],
        "location_name": location["location_name"],
        "campaign_id": campaign_id,
        "title": title,
        "detail": detail,
        "evidence": {"label": evidence_label, "value": evidence_value},
        "action": {"label": action_label, "href": action_href},
    }


def _percent_change(current: float, previous: float) -> float | None:
    if previous == 0:
        return None
    return round(((current - previous) / abs(previous)) * 100, 1)

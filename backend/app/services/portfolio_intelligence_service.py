from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.enums import StrategyRecommendationStatus
from app.models.campaign import Campaign
from app.models.intelligence import StrategyRecommendation
from app.services.account_hierarchy_service import build_account_hierarchy
from app.services.data_connections_service import get_connection_health


_STATE_ORDER = {
    "urgent": 0,
    "needs_attention": 1,
    "watch": 2,
    "on_track": 3,
}


def build_portfolio_overview(db: Session, *, organization_id: str) -> dict[str, Any]:
    """Rank locations by saved, explainable evidence without an opaque score."""

    hierarchy = build_account_hierarchy(db, organization_id=organization_id)
    connection_health = get_connection_health(db, organization_id)
    connections_by_location: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in connection_health["items"]:
        connections_by_location[str(item["location_id"])].append(item)

    open_actions_by_campaign = _open_action_counts(db, organization_id=organization_id)
    location_items: list[dict[str, Any]] = []
    for subaccount in hierarchy["subaccounts"]:
        for location in subaccount["business_locations"]:
            location_items.append(
                _location_overview(
                    location,
                    account_group={"id": subaccount["id"], "name": subaccount["name"]},
                    connections=connections_by_location.get(str(location["id"]), []),
                    open_actions_by_campaign=open_actions_by_campaign,
                )
            )
    for location in hierarchy["unassigned"]["business_locations"]:
        location_items.append(
            _location_overview(
                location,
                account_group=None,
                connections=connections_by_location.get(str(location["id"]), []),
                open_actions_by_campaign=open_actions_by_campaign,
            )
        )

    active_items = [item for item in location_items if item["location_status"] == "active"]
    active_items.sort(
        key=lambda item: (
            _STATE_ORDER[item["attention_state"]],
            -int(item["reason_count"]),
            str(item["location_name"]).lower(),
        )
    )
    archived_items = [item for item in location_items if item["location_status"] != "active"]
    archived_items.sort(key=lambda item: str(item["location_name"]).lower())
    ordered_items = [*active_items, *archived_items]
    shared_issues = _shared_issue_groups(active_items)
    repeatable_wins = _repeatable_win_candidates(active_items)

    counts = {
        "urgent": sum(item["attention_state"] == "urgent" for item in active_items),
        "needs_attention": sum(
            item["attention_state"] == "needs_attention" for item in active_items
        ),
        "watch": sum(item["attention_state"] == "watch" for item in active_items),
        "on_track": sum(item["attention_state"] == "on_track" for item in active_items),
    }
    locations_needing_attention = counts["urgent"] + counts["needs_attention"]
    top_attention = [
        item for item in active_items if item["attention_state"] != "on_track"
    ][:3]
    if locations_needing_attention:
        headline = (
            f"{locations_needing_attention} location"
            f"{'s' if locations_needing_attention != 1 else ''} need attention"
        )
        next_step = top_attention[0]["next_action"]["label"] if top_attention else None
    elif counts["watch"]:
        headline = (
            f"Keep an eye on {counts['watch']} location"
            f"{'s' if counts['watch'] != 1 else ''}"
        )
        next_step = top_attention[0]["next_action"]["label"] if top_attention else None
    elif active_items:
        headline = "Every active location is on track"
        next_step = "Keep following the saved action plans for each location."
    else:
        headline = "Add the first active business location"
        next_step = "Create a location before comparing portfolio performance."

    return {
        "organization_id": organization_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "summary": {
            "headline": headline,
            "next_step": next_step,
            "active_locations": len(active_items),
            "archived_locations": len(archived_items),
            "locations_with_saved_performance": sum(
                bool(item["performance"]["data_available"]) for item in active_items
            ),
            "locations_needing_attention": locations_needing_attention,
            **counts,
        },
        "top_attention": top_attention,
        "shared_issues": shared_issues,
        "repeatable_wins": repeatable_wins,
        "locations": ordered_items,
    }


def _shared_issue_groups(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group matching reasons while preserving every location's evidence."""

    grouped: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = defaultdict(list)
    for item in items:
        for reason in item["reasons"]:
            grouped[str(reason["code"])].append((item, reason))

    results: list[dict[str, Any]] = []
    for code, entries in grouped.items():
        if len(entries) < 2:
            continue
        entries.sort(key=lambda entry: str(entry[0]["location_name"]).lower())
        severity = min(
            (str(reason["severity"]) for _, reason in entries),
            key=lambda value: _STATE_ORDER[value],
        )
        first_reason = entries[0][1]
        results.append(
            {
                "code": code,
                "severity": severity,
                "attention_label": _attention_label(severity),
                "title": first_reason["title"],
                "summary": (
                    f"{len(entries)} locations show this same problem. "
                    "Review the saved evidence for each one before assigning shared work."
                ),
                "location_count": len(entries),
                "locations": [
                    {
                        "location_id": item["location_id"],
                        "location_name": item["location_name"],
                        "city": item.get("city"),
                        "region": item.get("region"),
                        "campaign_id": item.get("campaign_id"),
                        "detail": reason["detail"],
                        "evidence": reason.get("evidence"),
                        "action_label": reason["action_label"],
                        "action_href": reason["action_href"],
                    }
                    for item, reason in entries
                ],
            }
        )
    results.sort(
        key=lambda item: (
            _STATE_ORDER[str(item["severity"])],
            -int(item["location_count"]),
            str(item["title"]).lower(),
        )
    )
    return results


def _repeatable_win_candidates(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Surface evidence-backed examples to inspect, never unproven causal claims."""

    measured = [item for item in items if item["performance"]["data_available"]]
    candidates: list[dict[str, Any]] = []
    search_candidate = _search_visibility_candidate(measured)
    if search_candidate:
        candidates.append(search_candidate)
    review_candidate = _review_momentum_candidate(measured)
    if review_candidate:
        candidates.append(review_candidate)
    website_candidate = _website_health_candidate(measured)
    if website_candidate:
        candidates.append(website_candidate)
    return candidates


def _search_visibility_candidate(items: list[dict[str, Any]]) -> dict[str, Any] | None:
    ranked = [item for item in items if item["performance"]["avg_position"] is not None]
    if len(ranked) < 2:
        return None
    source = min(ranked, key=lambda item: float(item["performance"]["avg_position"]))
    source_position = float(source["performance"]["avg_position"])
    if source_position > 10:
        return None
    targets = [
        item
        for item in ranked
        if item["location_id"] != source["location_id"]
        and float(item["performance"]["avg_position"]) >= max(10.0, source_position + 4.0)
    ]
    if not targets:
        return None
    targets.sort(key=lambda item: float(item["performance"]["avg_position"]), reverse=True)
    return _win_candidate(
        code="search_visibility_example",
        title=f"Learn from {source['location_name']}'s stronger search visibility",
        summary=(
            f"{source['location_name']} is averaging about #{source_position:.1f}, while "
            f"{len(targets)} other location{'s are' if len(targets) != 1 else ' is'} further down. "
            "Compare its leading pages and searches before reusing any approach."
        ),
        source=source,
        source_metric={"label": "Average Google position", "value": round(source_position, 1)},
        targets=targets,
        target_metric=lambda item: {
            "label": "Average Google position",
            "value": round(float(item["performance"]["avg_position"]), 1),
        },
        action_label="Compare search rankings",
        action_href="/rankings",
    )


def _review_momentum_candidate(items: list[dict[str, Any]]) -> dict[str, Any] | None:
    reviewed = [
        item
        for item in items
        if item["performance"]["avg_rating_last_30d"] is not None
    ]
    if len(reviewed) < 2:
        return None
    source = max(
        reviewed,
        key=lambda item: (
            int(item["performance"]["reviews_last_30d"]),
            float(item["performance"]["avg_rating_last_30d"]),
        ),
    )
    source_reviews = int(source["performance"]["reviews_last_30d"])
    source_rating = float(source["performance"]["avg_rating_last_30d"])
    if source_reviews < 3 or source_rating < 4.5:
        return None
    targets = [
        item
        for item in reviewed
        if item["location_id"] != source["location_id"]
        and (
            int(item["performance"]["reviews_last_30d"]) <= max(1, source_reviews // 2)
            or float(item["performance"]["avg_rating_last_30d"]) < 4.5
        )
    ]
    if not targets:
        return None
    targets.sort(key=lambda item: int(item["performance"]["reviews_last_30d"]))
    return _win_candidate(
        code="review_momentum_example",
        title=f"Learn from {source['location_name']}'s recent review momentum",
        summary=(
            f"{source['location_name']} recorded {source_reviews} recent reviews at "
            f"{source_rating:.1f} stars. Compare its approved review routine with "
            f"{len(targets)} location{'s' if len(targets) != 1 else ''} that may need help."
        ),
        source=source,
        source_metric={
            "label": "Recent reviews and rating",
            "value": f"{source_reviews} reviews at {source_rating:.1f} stars",
        },
        targets=targets,
        target_metric=lambda item: {
            "label": "Recent reviews and rating",
            "value": (
                f"{int(item['performance']['reviews_last_30d'])} reviews at "
                f"{float(item['performance']['avg_rating_last_30d']):.1f} stars"
            ),
        },
        action_label="Compare customer reviews",
        action_href="/reviews",
    )


def _website_health_candidate(items: list[dict[str, Any]]) -> dict[str, Any] | None:
    if len(items) < 2:
        return None
    source = min(items, key=lambda item: int(item["performance"]["technical_issue_count"]))
    if int(source["performance"]["technical_issue_count"]) != 0:
        return None
    targets = [
        item
        for item in items
        if item["location_id"] != source["location_id"]
        and int(item["performance"]["technical_issue_count"]) > 0
    ]
    if not targets:
        return None
    targets.sort(key=lambda item: int(item["performance"]["technical_issue_count"]), reverse=True)
    return _win_candidate(
        code="website_health_example",
        title=f"Use {source['location_name']}'s healthy website as a comparison",
        summary=(
            f"The latest saved check found no website problems for {source['location_name']}, "
            f"while {len(targets)} other location{'s have' if len(targets) != 1 else ' has'} issues. "
            "Compare the setup before turning it into a shared checklist."
        ),
        source=source,
        source_metric={"label": "Website problems", "value": 0},
        targets=targets,
        target_metric=lambda item: {
            "label": "Website problems",
            "value": int(item["performance"]["technical_issue_count"]),
        },
        action_label="Compare website health",
        action_href="/site-health",
    )


def _win_candidate(
    *,
    code: str,
    title: str,
    summary: str,
    source: dict[str, Any],
    source_metric: dict[str, Any],
    targets: list[dict[str, Any]],
    target_metric: Any,
    action_label: str,
    action_href: str,
) -> dict[str, Any]:
    return {
        "code": code,
        "title": title,
        "summary": summary,
        "source": {
            "location_id": source["location_id"],
            "location_name": source["location_name"],
            "campaign_id": source.get("campaign_id"),
            "metric": source_metric,
        },
        "targets": [
            {
                "location_id": item["location_id"],
                "location_name": item["location_name"],
                "campaign_id": item.get("campaign_id"),
                "metric": target_metric(item),
            }
            for item in targets
        ],
        "action": {
            "label": action_label,
            "href": action_href,
            "campaign_id": source.get("campaign_id"),
        },
        "guardrail": (
            "This is a comparison clue, not proof that one tactic caused the result. "
            "Review the evidence before copying anything."
        ),
    }


def _open_action_counts(db: Session, *, organization_id: str) -> dict[str, int]:
    closed_states = {
        StrategyRecommendationStatus.EXECUTED,
        StrategyRecommendationStatus.ROLLED_BACK,
        StrategyRecommendationStatus.ARCHIVED,
    }
    rows = (
        db.query(StrategyRecommendation.campaign_id, func.count(StrategyRecommendation.id))
        .join(Campaign, Campaign.id == StrategyRecommendation.campaign_id)
        .filter(
            Campaign.organization_id == organization_id,
            StrategyRecommendation.status.notin_(closed_states),
        )
        .group_by(StrategyRecommendation.campaign_id)
        .all()
    )
    return {str(campaign_id): int(count) for campaign_id, count in rows}


def _location_overview(
    location: dict[str, Any],
    *,
    account_group: dict[str, str] | None,
    connections: list[dict[str, Any]],
    open_actions_by_campaign: dict[str, int],
) -> dict[str, Any]:
    campaigns = list(location.get("campaigns") or [])
    campaign_ids = [str(item["id"]) for item in campaigns]
    primary_campaign_id = campaign_ids[0] if campaign_ids else None
    open_actions = sum(open_actions_by_campaign.get(campaign_id, 0) for campaign_id in campaign_ids)
    performance = dict(location.get("performance") or {})
    reasons: list[dict[str, Any]] = []

    if account_group is None:
        reasons.append(
            _reason(
                code="account_group_missing",
                severity="urgent",
                title="Assign this location to the right business group",
                detail="This location is not organized with the rest of the business yet.",
                action_label="Finish location setup",
                action_href="/locations#location-setup",
            )
        )
    if not campaigns:
        reasons.append(
            _reason(
                code="campaign_missing",
                severity="urgent",
                title="Connect this location's website",
                detail="Search results and recommended actions cannot stay separate until its website is connected.",
                action_label="Connect this location",
                action_href="/locations#location-setup",
            )
        )

    broken_connections = [item for item in connections if item["display_state"] == "needs_attention"]
    unfinished_connections = [item for item in connections if item["display_state"] == "needs_setup"]
    if broken_connections:
        labels = ", ".join(str(item["label"]) for item in broken_connections[:2])
        reasons.append(
            _reason(
                code="connection_needs_attention",
                severity="urgent",
                title="Restore automatic updates",
                detail=f"{labels} {'need' if len(broken_connections) != 1 else 'needs'} attention.",
                action_label=str(broken_connections[0]["recovery_action"]["label"]),
                action_href=broken_connections[0]["recovery_action"].get("href") or "/settings",
                evidence={"label": "Connections needing attention", "value": len(broken_connections)},
            )
        )
    elif unfinished_connections:
        reasons.append(
            _reason(
                code="connection_setup_incomplete",
                severity="needs_attention",
                title="Finish connecting this location's data",
                detail=(
                    f"{len(unfinished_connections)} automatic data source"
                    f"{'s are' if len(unfinished_connections) != 1 else ' is'} not fully set up."
                ),
                action_label=str(unfinished_connections[0]["recovery_action"]["label"]),
                action_href=unfinished_connections[0]["recovery_action"].get("href") or "/settings",
                evidence={"label": "Connections left to finish", "value": len(unfinished_connections)},
            )
        )

    if campaigns and not performance.get("data_available"):
        reasons.append(
            _reason(
                code="performance_missing",
                severity="needs_attention",
                title="Collect the first performance check",
                detail="There is not enough saved information to compare this location with the others yet.",
                action_label="Check connection health",
                action_href="/settings",
            )
        )
    elif performance.get("data_available"):
        _add_performance_reasons(reasons, performance)

    if open_actions:
        reasons.append(
            _reason(
                code="open_actions",
                severity="watch",
                title="Work through the saved action list",
                detail=(
                    f"{open_actions} action{'s are' if open_actions != 1 else ' is'} still open for this location."
                ),
                action_label="Open this location's next steps",
                action_href="/opportunities",
                evidence={"label": "Open actions", "value": open_actions},
            )
        )

    reasons.sort(
        key=lambda reason: (
            _STATE_ORDER[str(reason["severity"])],
            str(reason["title"]).lower(),
        )
    )
    attention_state = str(reasons[0]["severity"]) if reasons else "on_track"
    next_action = (
        {
            "label": reasons[0]["action_label"],
            "href": reasons[0]["action_href"],
            "campaign_id": primary_campaign_id,
        }
        if reasons
        else {
            "label": "Open location overview",
            "href": "/dashboard",
            "campaign_id": primary_campaign_id,
        }
    )
    connection_counts = {
        "healthy": sum(item["display_state"] == "healthy" for item in connections),
        "updating": sum(item["display_state"] == "updating" for item in connections),
        "needs_attention": len(broken_connections),
        "needs_setup": len(unfinished_connections),
    }
    return {
        "location_id": location["id"],
        "location_name": location["name"],
        "location_status": location["status"],
        "city": location.get("city") or location.get("primary_city"),
        "region": location.get("region"),
        "account_group": account_group,
        "campaign_id": primary_campaign_id,
        "campaign_count": len(campaigns),
        "attention_state": attention_state,
        "attention_label": _attention_label(attention_state),
        "reason_count": len(reasons),
        "reasons": reasons,
        "next_action": next_action,
        "connections": connection_counts,
        "open_actions": open_actions,
        "performance": {
            "data_available": bool(performance.get("data_available")),
            "as_of": performance.get("as_of"),
            "clicks": int(performance.get("clicks") or 0),
            "impressions": int(performance.get("impressions") or 0),
            "avg_position": performance.get("avg_position"),
            "technical_issue_count": int(performance.get("technical_issue_count") or 0),
            "reviews_last_30d": int(performance.get("reviews_last_30d") or 0),
            "avg_rating_last_30d": performance.get("avg_rating_last_30d"),
        },
    }


def _add_performance_reasons(reasons: list[dict[str, Any]], performance: dict[str, Any]) -> None:
    as_of = _as_date(performance.get("as_of"))
    if as_of is not None and (datetime.now(UTC).date() - as_of).days > 14:
        reasons.append(
            _reason(
                code="portfolio_data_old",
                severity="needs_attention",
                title="Refresh this location's comparison data",
                detail="The saved portfolio comparison is more than two weeks old.",
                action_label="Check connection health",
                action_href="/settings",
                evidence={"label": "Newest comparison date", "value": as_of.isoformat()},
            )
        )

    technical_issues = int(performance.get("technical_issue_count") or 0)
    if technical_issues:
        reasons.append(
            _reason(
                code="website_issues",
                severity="needs_attention" if technical_issues >= 5 else "watch",
                title="Fix the website problems already found",
                detail=f"The latest saved check found {technical_issues} website problem{'s' if technical_issues != 1 else ''}.",
                action_label="Open website health",
                action_href="/site-health",
                evidence={"label": "Website problems", "value": technical_issues},
            )
        )

    position = performance.get("avg_position")
    if position is not None and float(position) > 10:
        reasons.append(
            _reason(
                code="search_position",
                severity="needs_attention" if float(position) > 20 else "watch",
                title="Improve searches that are not near the top",
                detail=f"The latest average Google position is about #{float(position):.1f}.",
                action_label="Open search rankings",
                action_href="/rankings",
                evidence={"label": "Average Google position", "value": round(float(position), 1)},
            )
        )

    rating = performance.get("avg_rating_last_30d")
    if rating is not None and float(rating) < 4.5:
        reasons.append(
            _reason(
                code="review_rating",
                severity="needs_attention" if float(rating) < 4.0 else "watch",
                title="Strengthen the recent customer rating",
                detail=f"The latest saved 30-day rating is {float(rating):.1f} stars.",
                action_label="Open customer reviews",
                action_href="/reviews",
                evidence={"label": "Recent rating", "value": round(float(rating), 1)},
            )
        )

    reviews = int(performance.get("reviews_last_30d") or 0)
    if reviews == 0:
        reasons.append(
            _reason(
                code="review_pace",
                severity="watch",
                title="Ask recent customers for honest reviews",
                detail="No new reviews are recorded in the latest 30-day comparison.",
                action_label="Open customer reviews",
                action_href="/reviews",
                evidence={"label": "New reviews in 30 days", "value": 0},
            )
        )


def _reason(
    *,
    code: str,
    severity: str,
    title: str,
    detail: str,
    action_label: str,
    action_href: str,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "title": title,
        "detail": detail,
        "action_label": action_label,
        "action_href": action_href,
        "evidence": evidence,
    }


def _attention_label(state: str) -> str:
    return {
        "urgent": "Fix first",
        "needs_attention": "Needs attention",
        "watch": "Keep an eye on this",
        "on_track": "On track",
    }[state]


def _as_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None

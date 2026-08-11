from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from statistics import median
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.business_location import BusinessLocation
from app.models.campaign import Campaign
from app.models.reputation import ReputationReview


THEME_TAXONOMY_VERSION = "service-review-themes-v1"
THEME_WINDOW_DAYS = 180
TREND_WEEKS = 12

THEMES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("communication", "Communication", ("call", "called", "text", "communication", "respond", "reply", "notified", "update")),
    ("arrival", "Arrival and scheduling", ("late", "early", "on time", "arrival", "arrived", "schedule", "appointment", "no show")),
    ("professionalism", "Professionalism", ("professional", "courteous", "polite", "respectful", "friendly", "rude")),
    ("work_quality", "Quality of work", ("quality", "careful", "damage", "damaged", "clean", "cleanup", "thorough", "mess")),
    ("speed", "Speed", ("fast", "quick", "prompt", "slow", "hours", "waited", "waiting")),
    ("price", "Price and estimates", ("price", "pricing", "cost", "expensive", "affordable", "estimate", "quote", "fee")),
    ("team", "Crew and staff", ("crew", "team", "staff", "driver", "technician", "employee", "workers")),
)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _round(value: float | None, digits: int = 1) -> float | None:
    return round(value, digits) if value is not None else None


def _campaign_context(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
) -> tuple[Campaign, BusinessLocation]:
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
    location = db.get(BusinessLocation, campaign.business_location_id)
    if location is None or location.organization_id != organization_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Choose a business location before reviewing reputation results.",
        )
    return campaign, location


def _owned_reviews_for_campaign(db: Session, campaign_id: str) -> list[ReputationReview]:
    return (
        db.query(ReputationReview)
        .filter(
            ReputationReview.campaign_id == campaign_id,
            ReputationReview.source_type == "owned_profile",
        )
        .order_by(ReputationReview.reviewed_at.desc())
        .all()
    )


def _rating_sentiment(rating: float) -> str:
    if rating >= 4:
        return "positive"
    if rating <= 2:
        return "negative"
    return "mixed"


def _metrics(rows: list[ReputationReview], *, now: datetime) -> dict[str, Any]:
    current_start = now - timedelta(days=30)
    previous_start = current_start - timedelta(days=30)
    current = [row for row in rows if _as_utc(row.reviewed_at) >= current_start]
    previous = [
        row
        for row in rows
        if previous_start <= _as_utc(row.reviewed_at) < current_start
    ]
    answerable = [row for row in rows if row.response_status in {"unanswered", "responded"}]
    responded = [row for row in answerable if row.response_status == "responded"]
    response_hours = [
        max(
            0.0,
            (
                _as_utc(row.response_updated_at) - _as_utc(row.reviewed_at)
            ).total_seconds()
            / 3600,
        )
        for row in responded
        if row.response_updated_at is not None
    ]
    average_rating = sum(float(row.rating) for row in rows) / len(rows) if rows else None
    current_average = (
        sum(float(row.rating) for row in current) / len(current) if current else None
    )
    previous_average = (
        sum(float(row.rating) for row in previous) / len(previous) if previous else None
    )
    response_rate = (len(responded) / len(answerable) * 100) if answerable else None
    unanswered = [row for row in answerable if row.response_status == "unanswered"]
    urgent_unanswered = [
        row
        for row in unanswered
        if float(row.rating) <= 2 and _as_utc(row.reviewed_at) >= now - timedelta(days=14)
    ]
    return {
        "total_reviews": len(rows),
        "average_rating": _round(average_rating, 2),
        "reviews_last_30_days": len(current),
        "reviews_previous_30_days": len(previous),
        "review_pace_change": len(current) - len(previous),
        "average_rating_last_30_days": _round(current_average, 2),
        "average_rating_previous_30_days": _round(previous_average, 2),
        "rating_change": (
            _round(current_average - previous_average, 2)
            if current_average is not None and previous_average is not None
            else None
        ),
        "positive_reviews_last_30_days": sum(float(row.rating) >= 4 for row in current),
        "mixed_reviews_last_30_days": sum(float(row.rating) == 3 for row in current),
        "negative_reviews_last_30_days": sum(float(row.rating) <= 2 for row in current),
        "unanswered_reviews": len(unanswered),
        "urgent_unanswered_reviews": len(urgent_unanswered),
        "answerable_reviews": len(answerable),
        "responded_reviews": len(responded),
        "response_rate_percent": _round(response_rate),
        "median_response_hours": _round(median(response_hours)) if response_hours else None,
        "response_time_sample_size": len(response_hours),
        "newest_review_at": (
            max(_as_utc(row.reviewed_at) for row in rows).isoformat() if rows else None
        ),
    }


def _weekly_trend(rows: list[ReputationReview], *, now: datetime) -> list[dict[str, Any]]:
    today = now.date()
    current_week_start = today - timedelta(days=today.weekday())
    first_week_start = current_week_start - timedelta(weeks=TREND_WEEKS - 1)
    buckets: dict[date, list[ReputationReview]] = defaultdict(list)
    for row in rows:
        reviewed_date = _as_utc(row.reviewed_at).date()
        week_start = reviewed_date - timedelta(days=reviewed_date.weekday())
        if first_week_start <= week_start <= current_week_start:
            buckets[week_start].append(row)
    result: list[dict[str, Any]] = []
    for index in range(TREND_WEEKS):
        week_start = first_week_start + timedelta(weeks=index)
        week_rows = buckets.get(week_start, [])
        result.append(
            {
                "week_start": week_start.isoformat(),
                "reviews_received": len(week_rows),
                "average_rating": (
                    _round(
                        sum(float(row.rating) for row in week_rows) / len(week_rows),
                        2,
                    )
                    if week_rows
                    else None
                ),
                "positive": sum(float(row.rating) >= 4 for row in week_rows),
                "mixed": sum(float(row.rating) == 3 for row in week_rows),
                "negative": sum(float(row.rating) <= 2 for row in week_rows),
            }
        )
    return result


def _themes(rows: list[ReputationReview], *, now: datetime) -> list[dict[str, Any]]:
    window_start = now - timedelta(days=THEME_WINDOW_DAYS)
    theme_rows: dict[str, dict[str, Any]] = {}
    for key, label, _terms in THEMES:
        theme_rows[key] = {
            "key": key,
            "label": label,
            "mentions": 0,
            "positive_mentions": 0,
            "mixed_mentions": 0,
            "negative_mentions": 0,
            "evidence_review_ids": [],
        }
    for row in rows:
        if _as_utc(row.reviewed_at) < window_start:
            continue
        body = str(row.body or "").strip().lower()
        if not body:
            continue
        sentiment = _rating_sentiment(float(row.rating))
        for key, _label, terms in THEMES:
            if not any(term in body for term in terms):
                continue
            item = theme_rows[key]
            item["mentions"] += 1
            item[f"{sentiment}_mentions"] += 1
            if len(item["evidence_review_ids"]) < 5:
                item["evidence_review_ids"].append(row.id)
    items = [item for item in theme_rows.values() if item["mentions"] > 0]
    for item in items:
        item["tone"] = (
            "needs_attention"
            if item["negative_mentions"] > item["positive_mentions"]
            else "strength"
            if item["positive_mentions"] > item["negative_mentions"]
            else "mixed"
        )
    return sorted(
        items,
        key=lambda item: (
            item["negative_mentions"],
            item["mentions"],
            item["positive_mentions"],
        ),
        reverse=True,
    )


def _actions(
    rows: list[ReputationReview],
    metrics: dict[str, Any],
    themes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    unanswered = [row for row in rows if row.response_status == "unanswered"]
    unanswered.sort(key=lambda row: (_as_utc(row.reviewed_at), float(row.rating)))
    if unanswered:
        actions.append(
            {
                "id": "answer_waiting_reviews",
                "priority": "high" if metrics["urgent_unanswered_reviews"] else "medium",
                "title": f"Reply to {len(unanswered)} waiting review{'s' if len(unanswered) != 1 else ''}",
                "why": (
                    "Start with the newest one- and two-star reviews. A timely response shows customers that the business is listening."
                    if metrics["urgent_unanswered_reviews"]
                    else "These customers have not received a saved business response yet."
                ),
                "metric_label": "Reviews still waiting for a reply",
                "current_value": len(unanswered),
                "target_value": 0,
                "evidence_review_ids": [row.id for row in unanswered[:5]],
            }
        )
    negative_themes = [
        item for item in themes if item["negative_mentions"] >= 2
    ][:3]
    for negative_theme in negative_themes:
        actions.append(
            {
                "id": f"review_theme_{negative_theme['key']}",
                "priority": "high",
                "title": f"Check the customer experience around {negative_theme['label'].lower()}",
                "why": f"{negative_theme['negative_mentions']} recent reviews mentioned this subject with a one- or two-star rating.",
                "metric_label": "Recent negative mentions",
                "current_value": negative_theme["negative_mentions"],
                "target_value": 0,
                "evidence_review_ids": negative_theme["evidence_review_ids"],
            }
        )
    if metrics["review_pace_change"] < 0:
        actions.append(
            {
                "id": "restore_review_pace",
                "priority": "medium",
                "title": "Ask recent customers for honest feedback more consistently",
                "why": f"This location received {abs(metrics['review_pace_change'])} fewer reviews than in the prior 30 days.",
                "metric_label": "Reviews received in 30 days",
                "current_value": metrics["reviews_last_30_days"],
                "target_value": metrics["reviews_previous_30_days"],
                "evidence_review_ids": [],
            }
        )
    if (
        metrics["median_response_hours"] is not None
        and metrics["median_response_hours"] > 48
        and metrics["response_time_sample_size"] >= 2
    ):
        actions.append(
            {
                "id": "improve_response_speed",
                "priority": "medium",
                "title": "Set a two-day review reply routine",
                "why": f"The typical saved reply took {metrics['median_response_hours']:.0f} hours during the measured sample.",
                "metric_label": "Typical reply time in hours",
                "current_value": metrics["median_response_hours"],
                "target_value": 48,
                "evidence_review_ids": [],
            }
        )
    if not actions:
        actions.append(
            {
                "id": "maintain_review_routine",
                "priority": "low",
                "title": "Keep the current review routine going",
                "why": "No measured review issue is large enough to create a corrective action right now.",
                "metric_label": "Reviews waiting for a reply",
                "current_value": metrics["unanswered_reviews"],
                "target_value": 0,
                "evidence_review_ids": [],
            }
        )
    priority_order = {"high": 0, "medium": 1, "low": 2}
    return sorted(actions, key=lambda item: priority_order[item["priority"]])


def _location_payload(
    *,
    campaign: Campaign,
    location: BusinessLocation,
    rows: list[ReputationReview],
    now: datetime,
) -> dict[str, Any]:
    metrics = _metrics(rows, now=now)
    themes = _themes(rows, now=now)
    return {
        "campaign_id": campaign.id,
        "business_location_id": location.id,
        "location_name": location.name,
        "city": location.city or location.primary_city,
        "region": location.region,
        "metrics": metrics,
        "weekly_trend": _weekly_trend(rows, now=now),
        "themes": themes,
        "actions": _actions(rows, metrics, themes),
        "evidence": {
            "source_scope": "authorized_owned_profile_reviews",
            "theme_taxonomy_version": THEME_TAXONOMY_VERSION,
            "theme_window_days": THEME_WINDOW_DAYS,
            "comparison_period_days": 30,
            "computed_at": now.isoformat(),
            "claims_limited_to_saved_reviews": True,
        },
    }


def location_intelligence(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    resolved_now = _as_utc(now or datetime.now(UTC))
    campaign, location = _campaign_context(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=campaign_id,
    )
    rows = _owned_reviews_for_campaign(db, campaign.id)
    return _location_payload(
        campaign=campaign,
        location=location,
        rows=rows,
        now=resolved_now,
    )


def _portfolio_outliers(locations: list[dict[str, Any]]) -> None:
    measured = [item for item in locations if item["metrics"]["total_reviews"] > 0]
    if len(measured) < 2:
        for item in locations:
            item["outliers"] = []
            item["attention_score"] = 0
        return
    ratings = [item["metrics"]["average_rating"] for item in measured]
    paces = [item["metrics"]["reviews_last_30_days"] for item in measured]
    unanswered_counts = [item["metrics"]["unanswered_reviews"] for item in measured]
    response_times = [
        item["metrics"]["median_response_hours"]
        for item in measured
        if item["metrics"]["median_response_hours"] is not None
    ]
    rating_mid = float(median(ratings))
    pace_mid = float(median(paces))
    unanswered_mid = float(median(unanswered_counts))
    response_mid = float(median(response_times)) if response_times else None
    for item in locations:
        metrics = item["metrics"]
        outliers: list[dict[str, str]] = []
        if metrics["total_reviews"] == 0:
            outliers.append(
                {"code": "no_review_data", "label": "No saved customer reviews yet"}
            )
        else:
            if metrics["average_rating"] <= rating_mid - 0.3 and metrics["total_reviews"] >= 3:
                outliers.append(
                    {"code": "rating_below_portfolio", "label": "Rating is below the other locations"}
                )
            if metrics["reviews_last_30_days"] <= pace_mid - 2:
                outliers.append(
                    {"code": "review_pace_below_portfolio", "label": "Fewer recent reviews than the other locations"}
                )
            if metrics["unanswered_reviews"] >= max(3, unanswered_mid + 2):
                outliers.append(
                    {"code": "unanswered_above_portfolio", "label": "More unanswered reviews than the other locations"}
                )
            if (
                response_mid is not None
                and metrics["median_response_hours"] is not None
                and metrics["response_time_sample_size"] >= 2
                and metrics["median_response_hours"] >= response_mid + 24
            ):
                outliers.append(
                    {"code": "response_slower_than_portfolio", "label": "Replies are slower than the other locations"}
                )
        item["outliers"] = outliers
        item["attention_score"] = len(outliers)


def portfolio_intelligence(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    resolved_now = _as_utc(now or datetime.now(UTC))
    campaigns = (
        db.query(Campaign)
        .filter(
            Campaign.tenant_id == tenant_id,
            Campaign.organization_id == organization_id,
            Campaign.business_location_id.isnot(None),
        )
        .order_by(Campaign.created_at.asc())
        .all()
    )
    locations_by_id = {
        location.id: location
        for location in db.query(BusinessLocation)
        .filter(
            BusinessLocation.organization_id == organization_id,
            BusinessLocation.status == "active",
        )
        .all()
    }
    active_campaigns: list[Campaign] = []
    seen_locations: set[str] = set()
    for campaign in campaigns:
        if campaign.business_location_id not in locations_by_id:
            continue
        if campaign.business_location_id in seen_locations:
            continue
        seen_locations.add(campaign.business_location_id)
        active_campaigns.append(campaign)
    campaign_ids = [campaign.id for campaign in active_campaigns]
    reviews = (
        db.query(ReputationReview)
        .filter(
            ReputationReview.campaign_id.in_(campaign_ids),
            ReputationReview.source_type == "owned_profile",
        )
        .all()
        if campaign_ids
        else []
    )
    rows_by_campaign: dict[str, list[ReputationReview]] = defaultdict(list)
    for review in reviews:
        rows_by_campaign[review.campaign_id].append(review)
    locations = [
        _location_payload(
            campaign=campaign,
            location=locations_by_id[campaign.business_location_id],
            rows=rows_by_campaign.get(campaign.id, []),
            now=resolved_now,
        )
        for campaign in active_campaigns
    ]
    _portfolio_outliers(locations)
    locations.sort(
        key=lambda item: (
            item["attention_score"],
            item["metrics"]["unanswered_reviews"],
            -(item["metrics"]["average_rating"] or 0),
        ),
        reverse=True,
    )
    total_reviews = sum(item["metrics"]["total_reviews"] for item in locations)
    total_rating_points = sum(
        (item["metrics"]["average_rating"] or 0) * item["metrics"]["total_reviews"]
        for item in locations
    )
    total_answerable = sum(
        item["metrics"]["answerable_reviews"] for item in locations
    )
    total_unanswered = sum(item["metrics"]["unanswered_reviews"] for item in locations)
    total_responded = sum(item["metrics"]["responded_reviews"] for item in locations)
    return {
        "summary": {
            "locations": len(locations),
            "locations_with_reviews": sum(
                item["metrics"]["total_reviews"] > 0 for item in locations
            ),
            "locations_needing_attention": sum(item["attention_score"] > 0 for item in locations),
            "total_reviews": total_reviews,
            "reviews_last_30_days": sum(
                item["metrics"]["reviews_last_30_days"] for item in locations
            ),
            "unanswered_reviews": total_unanswered,
            "average_rating": _round(total_rating_points / total_reviews, 2) if total_reviews else None,
            "response_rate_percent": (
                _round(total_responded / total_answerable * 100)
                if total_answerable
                else None
            ),
        },
        "locations": locations,
        "evidence": {
            "source_scope": "authorized_owned_profile_reviews",
            "comparison_requires_two_locations": True,
            "computed_at": resolved_now.isoformat(),
            "claims_limited_to_saved_reviews": True,
        },
    }

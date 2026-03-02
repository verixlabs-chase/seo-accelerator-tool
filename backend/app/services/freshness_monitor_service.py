from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.metrics import traffic_fact_stale_campaigns_total
from app.models.analytics_daily_metric import AnalyticsDailyMetric
from app.models.campaign import Campaign
from app.models.campaign_daily_metric import CampaignDailyMetric
from app.models.search_console_daily_metric import SearchConsoleDailyMetric

logger = logging.getLogger("lsos.traffic.freshness")


def get_data_freshness_summary(db: Session, *, evaluated_at: datetime | None = None) -> dict[str, object]:
    settings = get_settings()
    evaluated = evaluated_at or datetime.now(UTC)
    threshold = max(0, int(settings.traffic_fact_max_staleness_days))
    evaluation_date = evaluated.date()

    campaigns = (
        db.query(Campaign)
        .filter(
            Campaign.setup_state == "Active",
            Campaign.organization_id.isnot(None),
        )
        .order_by(Campaign.created_at.asc(), Campaign.id.asc())
        .all()
    )

    if not campaigns:
        return {
            "status": "healthy",
            "stale_campaign_count": 0,
            "max_staleness_days": 0,
            "evaluated_at": evaluated.isoformat(),
        }

    search_console_dates = _latest_metric_dates(db, SearchConsoleDailyMetric)
    analytics_dates = _latest_metric_dates(db, AnalyticsDailyMetric)
    campaign_daily_dates = _latest_metric_dates(db, CampaignDailyMetric)

    stale_campaign_count = 0
    max_staleness_days = 0
    has_degraded_campaign = False

    for campaign in campaigns:
        fallback_date = campaign.created_at.date() if campaign.created_at is not None else evaluation_date
        observed_dates = [
            search_console_dates.get(campaign.id),
            analytics_dates.get(campaign.id),
            campaign_daily_dates.get(campaign.id),
        ]
        available_dates = [metric_date for metric_date in observed_dates if metric_date is not None]
        anchor_date = min(available_dates) if available_dates else fallback_date
        if len(available_dates) != len(observed_dates):
            anchor_date = min(anchor_date, fallback_date)

        days_stale = max(0, (evaluation_date - anchor_date).days)
        max_staleness_days = max(max_staleness_days, days_stale)

        if days_stale > threshold:
            stale_campaign_count += 1
            logger.warning(
                "traffic_fact_stale_detected",
                extra={
                    "event": "traffic_fact_stale_detected",
                    "organization_id": str(campaign.organization_id or ""),
                    "campaign_id": str(campaign.id),
                    "days_stale": int(days_stale),
                },
            )
        elif days_stale > 0:
            has_degraded_campaign = True

    if settings.metrics_enabled and stale_campaign_count > 0:
        traffic_fact_stale_campaigns_total.inc(stale_campaign_count)

    status = "healthy"
    if stale_campaign_count > 0:
        status = "stale"
    elif has_degraded_campaign:
        status = "degraded"

    return {
        "status": status,
        "stale_campaign_count": stale_campaign_count,
        "max_staleness_days": max_staleness_days,
        "evaluated_at": evaluated.isoformat(),
    }


def _latest_metric_dates(db: Session, model: type[SearchConsoleDailyMetric] | type[AnalyticsDailyMetric] | type[CampaignDailyMetric]) -> dict[str, object]:
    rows = db.query(model.campaign_id, func.max(model.metric_date)).group_by(model.campaign_id).all()
    return {str(campaign_id): metric_date for campaign_id, metric_date in rows if campaign_id and metric_date is not None}

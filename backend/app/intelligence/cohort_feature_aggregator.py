from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.intelligence.feature_aggregator import describe_campaign_cohort
from app.models.campaign import Campaign
from app.models.campaign_daily_metric import CampaignDailyMetric
from app.models.recommendation_outcome import RecommendationOutcome
from app.models.temporal import TemporalSignalSnapshot

_SIGNAL_FIELDS = {
    'internal_link_ratio',
    'ranking_velocity',
    'technical_issue_density',
    'content_growth_rate',
}


def build_cohort_rows(db: Session) -> list[dict[str, Any]]:
    campaigns = db.query(Campaign).order_by(Campaign.id.asc()).all()
    rows: list[dict[str, Any]] = []

    for campaign in campaigns:
        cohort = describe_campaign_cohort(db, campaign.id)['cohort']
        daily_metrics = (
            db.query(CampaignDailyMetric)
            .filter(CampaignDailyMetric.campaign_id == campaign.id)
            .order_by(CampaignDailyMetric.metric_date.desc(), CampaignDailyMetric.id.desc())
            .limit(2)
            .all()
        )
        signal_values = _latest_signal_values(db, campaign.id)
        outcome_stats = _outcome_stats(db, campaign.id)

        traffic_growth = _traffic_growth(daily_metrics)
        technical_issue_count = float((daily_metrics[0].technical_issue_count if daily_metrics else 0) or 0)
        ranking_velocity = float(signal_values.get('ranking_velocity', 0.0) or 0.0)
        technical_issue_density = float(signal_values.get('technical_issue_density', technical_issue_count / 100.0) or 0.0)
        internal_link_ratio = float(signal_values.get('internal_link_ratio', 0.0) or 0.0)
        content_velocity = float(signal_values.get('content_growth_rate', 0.0) or 0.0)

        rows.append(
            {
                'campaign_id': campaign.id,
                'cohort_definition': cohort,
                'internal_link_ratio': round(internal_link_ratio, 6),
                'technical_issue_density': round(technical_issue_density, 6),
                'ranking_velocity': round(ranking_velocity, 6),
                'content_velocity': round(content_velocity, 6),
                'traffic_growth': round(traffic_growth, 6),
                'outcome_delta': round(float(outcome_stats['avg_delta']), 6),
                'outcome_positive_rate': round(float(outcome_stats['positive_rate']), 6),
            }
        )

    return rows


def aggregate_feature_profiles(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row['cohort_definition'])].append(row)

    profiles: list[dict[str, Any]] = []
    for cohort_definition in sorted(grouped):
        cohort_rows = grouped[cohort_definition]
        count = max(1, len(cohort_rows))
        profiles.append(
            {
                'cohort_definition': cohort_definition,
                'support_count': count,
                'avg_internal_link_ratio': round(sum(float(r['internal_link_ratio']) for r in cohort_rows) / count, 6),
                'avg_technical_issue_density': round(sum(float(r['technical_issue_density']) for r in cohort_rows) / count, 6),
                'avg_ranking_velocity': round(sum(float(r['ranking_velocity']) for r in cohort_rows) / count, 6),
                'avg_content_velocity': round(sum(float(r['content_velocity']) for r in cohort_rows) / count, 6),
                'avg_traffic_growth': round(sum(float(r['traffic_growth']) for r in cohort_rows) / count, 6),
                'avg_outcome_delta': round(sum(float(r['outcome_delta']) for r in cohort_rows) / count, 6),
                'avg_outcome_positive_rate': round(sum(float(r['outcome_positive_rate']) for r in cohort_rows) / count, 6),
            }
        )

    return profiles


def _latest_signal_values(db: Session, campaign_id: str) -> dict[str, float]:
    rows = (
        db.query(TemporalSignalSnapshot)
        .filter(
            TemporalSignalSnapshot.campaign_id == campaign_id,
            TemporalSignalSnapshot.metric_name.in_(_SIGNAL_FIELDS),
        )
        .order_by(TemporalSignalSnapshot.observed_at.desc(), TemporalSignalSnapshot.id.desc())
        .all()
    )

    values: dict[str, float] = {}
    for row in rows:
        metric = str(row.metric_name)
        if metric in values:
            continue
        values[metric] = float(row.metric_value)
    return values


def _outcome_stats(db: Session, campaign_id: str) -> dict[str, float]:
    avg_delta, positive_count, total_count = (
        db.query(
            func.coalesce(func.avg(RecommendationOutcome.delta), 0.0),
            func.coalesce(func.sum(case((RecommendationOutcome.delta > 0, 1), else_=0)), 0),
            func.count(RecommendationOutcome.id),
        )
        .filter(RecommendationOutcome.campaign_id == campaign_id)
        .one()
    )
    total = int(total_count or 0)
    positive_rate = (float(positive_count) / total) if total > 0 else 0.0
    return {'avg_delta': float(avg_delta or 0.0), 'positive_rate': positive_rate}


def _traffic_growth(metrics: list[CampaignDailyMetric]) -> float:
    if len(metrics) < 2:
        return 0.0
    current = float(metrics[0].sessions or 0)
    previous = float(metrics[1].sessions or 0)
    if previous <= 0:
        return 0.0 if current <= 0 else 1.0
    return (current - previous) / previous

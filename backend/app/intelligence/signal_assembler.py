from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.events import EventType, publish_event
from app.models.campaign import Campaign
from app.models.campaign_daily_metric import CampaignDailyMetric
from app.models.content import ContentAsset
from app.models.crawl import TechnicalIssue
from app.models.local import LocalHealthSnapshot, Review, ReviewVelocitySnapshot
from app.models.rank import Ranking
from app.models.temporal import MomentumMetric


def assemble_signals(campaign_id: str, db: Session | None = None, *, publish: bool = True) -> dict[str, float]:
    owns_session = db is None
    session = db or SessionLocal()
    try:
        campaign = session.get(Campaign, campaign_id)
        if campaign is None:
            raise ValueError(f'Campaign not found: {campaign_id}')

        technical_issue_count = int(
            session.query(TechnicalIssue)
            .filter(TechnicalIssue.campaign_id == campaign_id)
            .count()
        )

        avg_rank = float(
            session.query(func.avg(Ranking.current_position))
            .filter(Ranking.campaign_id == campaign_id)
            .scalar()
            or 100.0
        )

        avg_position_delta = float(
            session.query(func.avg(Ranking.delta))
            .filter(Ranking.campaign_id == campaign_id, Ranking.delta.isnot(None))
            .scalar()
            or 0.0
        )

        content_count = int(
            session.query(ContentAsset)
            .filter(ContentAsset.campaign_id == campaign_id, ContentAsset.status == 'published')
            .count()
        )

        local_health_row = (
            session.query(LocalHealthSnapshot)
            .filter(LocalHealthSnapshot.campaign_id == campaign_id)
            .order_by(LocalHealthSnapshot.captured_at.desc())
            .first()
        )
        local_health_score = float(local_health_row.health_score) if local_health_row is not None else 50.0
        local_health = _normalize_health(local_health_score)

        latest_metric = (
            session.query(CampaignDailyMetric)
            .filter(CampaignDailyMetric.campaign_id == campaign_id)
            .order_by(CampaignDailyMetric.metric_date.desc(), CampaignDailyMetric.id.desc())
            .first()
        )

        clicks = float(getattr(latest_metric, 'clicks', 0) or 0)
        impressions = float(getattr(latest_metric, 'impressions', 0) or 0)
        sessions = float(getattr(latest_metric, 'sessions', 0) or 0)
        conversions = float(getattr(latest_metric, 'conversions', 0) or 0)
        ctr = (clicks / impressions) if impressions > 0 else 0.0

        traffic_growth_percent = _compute_traffic_growth_percent(session, campaign_id)

        momentum = (
            session.query(MomentumMetric)
            .filter(MomentumMetric.campaign_id == campaign_id)
            .order_by(MomentumMetric.computed_at.desc(), MomentumMetric.id.desc())
            .first()
        )
        ranking_velocity = float(-momentum.slope) if momentum is not None else 0.0

        velocity_row = (
            session.query(ReviewVelocitySnapshot)
            .filter(ReviewVelocitySnapshot.campaign_id == campaign_id)
            .order_by(ReviewVelocitySnapshot.captured_at.desc(), ReviewVelocitySnapshot.id.desc())
            .first()
        )
        review_velocity = float(velocity_row.reviews_last_30d) if velocity_row is not None else 0.0
        avg_rating = float(velocity_row.avg_rating_last_30d) if velocity_row is not None else 0.0
        review_count = float(
            session.query(Review)
            .filter(Review.campaign_id == campaign_id)
            .count()
        )

        payload = {
            'technical_issue_count': float(technical_issue_count),
            'avg_rank': round(avg_rank, 4),
            'avg_position': round(avg_rank, 4),
            'position_delta': round(avg_position_delta, 4),
            'content_count': float(content_count),
            'local_health': round(local_health, 4),
            'crawl_errors': float(technical_issue_count),
            'clicks': round(clicks, 4),
            'impressions': round(impressions, 4),
            'ctr': round(ctr, 6),
            'sessions': round(sessions, 4),
            'conversions': round(conversions, 4),
            'traffic_growth_percent': round(traffic_growth_percent, 6),
            'ranking_velocity': round(ranking_velocity, 6),
            'review_velocity': round(review_velocity, 6),
            'review_count': round(review_count, 6),
            'avg_rating': round(avg_rating, 6),
        }

        if publish:
            publish_event(
                EventType.SIGNAL_UPDATED.value,
                {
                    'campaign_id': campaign_id,
                    'signal_keys': sorted(payload.keys()),
                    'signals': payload,
                    'observed_at': datetime.now(UTC).isoformat(),
                },
            )

        return payload
    finally:
        if owns_session:
            session.close()


def _normalize_health(score: float) -> float:
    if score <= 1.0:
        return max(0.0, min(score, 1.0))
    return max(0.0, min(score / 100.0, 1.0))


def _compute_traffic_growth_percent(db: Session, campaign_id: str) -> float:
    rows = (
        db.query(CampaignDailyMetric)
        .filter(CampaignDailyMetric.campaign_id == campaign_id)
        .order_by(CampaignDailyMetric.metric_date.desc(), CampaignDailyMetric.id.desc())
        .limit(2)
        .all()
    )
    if len(rows) < 2:
        return 0.0
    current = float(rows[0].sessions or 0)
    previous = float(rows[1].sessions or 0)
    if previous <= 0:
        return 0.0 if current <= 0 else 1.0
    return (current - previous) / previous


def recent_window_bounds(days: int = 30) -> tuple[datetime, datetime]:
    end = datetime.now(UTC)
    start = end - timedelta(days=max(1, days))
    return start, end

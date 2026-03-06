from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.events import EventType, publish_event
from app.intelligence.signal_assembler import assemble_signals
from app.intelligence.temporal_ingestion import write_temporal_signals
from app.models.content import ContentAsset
from app.models.crawl import CrawlPageResult, TechnicalIssue
from app.models.temporal import MomentumMetric, TemporalSignalSnapshot


def compute_features(
    campaign_id: str,
    db: Session | None = None,
    *,
    persist: bool = True,
    publish: bool = True,
) -> dict[str, float]:
    owns_session = db is None
    session = db or SessionLocal()
    try:
        signals = assemble_signals(campaign_id, db=session, publish=False)

        technical_issue_count = float(signals.get('technical_issue_count', 0.0))
        content_count = max(float(signals.get('content_count', 0.0)), 1.0)

        crawled_pages = float(
            session.query(CrawlPageResult)
            .filter(CrawlPageResult.campaign_id == campaign_id)
            .count()
        )
        crawled_pages = max(crawled_pages, 1.0)

        no_internal_links = float(
            session.query(TechnicalIssue)
            .filter(TechnicalIssue.campaign_id == campaign_id, TechnicalIssue.issue_code == 'no_internal_links')
            .count()
        )

        technical_issue_density = technical_issue_count / crawled_pages
        internal_link_ratio = max(0.0, min(1.0, (crawled_pages - no_internal_links) / crawled_pages))

        momentum = (
            session.query(MomentumMetric)
            .filter(MomentumMetric.campaign_id == campaign_id)
            .order_by(MomentumMetric.computed_at.desc(), MomentumMetric.id.desc())
            .first()
        )
        ranking_velocity = float(-momentum.slope) if momentum is not None else 0.0

        content_growth_rate = _content_growth_rate(session, campaign_id)

        features = {
            'technical_issue_density': round(technical_issue_density, 6),
            'internal_link_ratio': round(internal_link_ratio, 6),
            'ranking_velocity': round(ranking_velocity, 6),
            'content_growth_rate': round(content_growth_rate, 6),
            'crawl_health_score': round(max(0.0, min(1.0, 1.0 - technical_issue_density)), 6),
            'content_per_issue': round(content_count / max(technical_issue_count, 1.0), 6),
        }

        if persist:
            write_temporal_signals(
                campaign_id,
                features,
                db=session,
                observed_at=datetime.now(UTC),
                source='feature_store_v1',
            )
            if owns_session:
                session.commit()

        if publish:
            publish_event(
                EventType.FEATURE_UPDATED.value,
                {
                    'campaign_id': campaign_id,
                    'changed_features': sorted(features.keys()),
                    'features': features,
                    'computed_at': datetime.now(UTC).isoformat(),
                },
            )

        return features
    finally:
        if owns_session:
            session.close()


def _content_growth_rate(db: Session, campaign_id: str, days: int = 30) -> float:
    now = datetime.now(UTC)
    start = now - timedelta(days=max(1, days))

    published_now = float(
        db.query(ContentAsset)
        .filter(ContentAsset.campaign_id == campaign_id, ContentAsset.status == 'published')
        .count()
    )

    historical = (
        db.query(TemporalSignalSnapshot)
        .filter(
            TemporalSignalSnapshot.campaign_id == campaign_id,
            TemporalSignalSnapshot.metric_name == 'content_count',
            TemporalSignalSnapshot.observed_at <= start,
        )
        .order_by(TemporalSignalSnapshot.observed_at.desc(), TemporalSignalSnapshot.id.desc())
        .first()
    )
    if historical is None:
        return 0.0

    previous = float(historical.metric_value)
    if previous <= 0:
        return 0.0 if published_now <= 0 else 1.0
    return (published_now - previous) / previous

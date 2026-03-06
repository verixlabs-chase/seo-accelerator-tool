from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.intelligence.feature_store import compute_features
from app.intelligence.signal_assembler import assemble_signals
from app.models.crawl import CrawlPageResult


@dataclass(frozen=True)
class DigitalTwinState:
    campaign_id: str
    avg_rank: float
    traffic_estimate: float
    technical_issue_count: int
    internal_link_count: int
    content_page_count: int
    review_velocity: float
    local_health_score: float
    momentum_score: float

    @classmethod
    def from_campaign_data(cls, db: Session, campaign_id: str) -> 'DigitalTwinState':
        signals = assemble_signals(campaign_id, db=db, publish=False)
        features = compute_features(campaign_id, db=db, persist=False, publish=False)

        crawl_page_count = int(
            db.query(func.count(CrawlPageResult.id))
            .filter(CrawlPageResult.campaign_id == campaign_id)
            .scalar()
            or 0
        )

        internal_link_ratio = float(features.get('internal_link_ratio', 1.0) or 1.0)
        internal_link_count = max(0, int(round(crawl_page_count * internal_link_ratio)))

        return cls(
            campaign_id=campaign_id,
            avg_rank=float(signals.get('avg_rank', 100.0) or 100.0),
            traffic_estimate=float(signals.get('sessions', 0.0) or 0.0),
            technical_issue_count=int(float(signals.get('technical_issue_count', 0.0) or 0.0)),
            internal_link_count=internal_link_count,
            content_page_count=int(float(signals.get('content_count', 0.0) or 0.0)),
            review_velocity=float(signals.get('review_velocity', 0.0) or 0.0),
            local_health_score=float(signals.get('local_health', 0.0) or 0.0),
            momentum_score=float(signals.get('ranking_velocity', 0.0) or 0.0),
        )

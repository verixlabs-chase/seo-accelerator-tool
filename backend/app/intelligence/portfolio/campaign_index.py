from __future__ import annotations

from app.intelligence.portfolio.portfolio_models import CampaignPerformanceSnapshot


def _normalize_velocity(value: float) -> float:
    return max(0.0, min(float(value), 1.0))


def calculate_campaign_performance_score(
    *,
    ranking_velocity: float,
    content_velocity: float,
    link_velocity: float,
    review_velocity: float,
) -> float:
    velocities = [
        _normalize_velocity(ranking_velocity),
        _normalize_velocity(content_velocity),
        _normalize_velocity(link_velocity),
        _normalize_velocity(review_velocity),
    ]
    return round(sum(velocities) / len(velocities), 6)


def build_campaign_index(*, campaign_id: str, ranking_velocity: float, content_velocity: float, link_velocity: float, review_velocity: float) -> CampaignPerformanceSnapshot:
    return CampaignPerformanceSnapshot(
        campaign_id=campaign_id,
        ranking_velocity=ranking_velocity,
        content_velocity=content_velocity,
        link_velocity=link_velocity,
        review_velocity=review_velocity,
        campaign_performance_score=calculate_campaign_performance_score(
            ranking_velocity=ranking_velocity,
            content_velocity=content_velocity,
            link_velocity=link_velocity,
            review_velocity=review_velocity,
        ),
    )


def rank_campaigns(items: list[CampaignPerformanceSnapshot]) -> list[CampaignPerformanceSnapshot]:
    return sorted(
        items,
        key=lambda item: (-item.campaign_performance_score, item.campaign_id),
    )

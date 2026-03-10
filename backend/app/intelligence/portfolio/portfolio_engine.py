from __future__ import annotations

from sqlalchemy.orm import Session

from app.intelligence.causal.causal_query_engine import get_policy_preference_map
from app.intelligence.experiments.experiment_engine import apply_experiment_assignments
from app.intelligence.portfolio.policy_performance import update_policy_performance
from app.intelligence.portfolio.portfolio_models import PolicyPerformanceSnapshot, PortfolioAllocationResult
from app.intelligence.portfolio.strategy_allocator import allocate_strategies
from app.models.policy_performance import PolicyPerformance
from app.models.recommendation_outcome import RecommendationOutcome


def run_portfolio_cycle(db: Session, outcome: RecommendationOutcome) -> PortfolioAllocationResult | None:
    updated = update_policy_performance(db, outcome)
    if updated is None:
        return None

    policy_rows = (
        db.query(PolicyPerformance)
        .filter(PolicyPerformance.industry == updated.industry)
        .order_by(PolicyPerformance.success_score.desc(), PolicyPerformance.policy_id.asc())
        .limit(50)
        .all()
    )
    preferences = get_policy_preference_map(db, updated.industry)
    snapshots = []
    for row in policy_rows:
        preference = preferences.get(row.policy_id)
        success_score = float(row.success_score)
        confidence = float(row.confidence)
        if preference is not None:
            success_score = round(success_score + (preference.effect_size * preference.confidence), 6)
            confidence = round(min(1.0, max(confidence, preference.confidence)), 6)
        snapshots.append(
            PolicyPerformanceSnapshot(
                policy_id=row.policy_id,
                campaign_id=row.campaign_id,
                industry=row.industry,
                success_score=success_score,
                execution_count=int(row.execution_count),
                confidence=confidence,
            )
        )
    allocations = allocate_strategies(snapshots, total_slots=min(3, len(snapshots)))
    assigned_allocations, _experiment_assignments = apply_experiment_assignments(
        db,
        campaign_id=outcome.campaign_id,
        industry=updated.industry,
        allocations=allocations,
    )
    return PortfolioAllocationResult(
        campaign_id=outcome.campaign_id,
        industry=updated.industry,
        updated_policy_id=updated.policy_id,
        allocations=assigned_allocations,
    )

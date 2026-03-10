from __future__ import annotations

from app.intelligence.portfolio.portfolio_models import PolicyAllocation, PolicyPerformanceSnapshot


def allocate_strategies(
    policy_rows: list[PolicyPerformanceSnapshot],
    *,
    total_slots: int | None = None,
    exploit_ratio: float = 0.7,
) -> list[PolicyAllocation]:
    if not policy_rows:
        return []

    limit = min(len(policy_rows), total_slots or len(policy_rows))
    ranked = sorted(
        policy_rows,
        key=lambda item: (-item.success_score, -item.confidence, -item.execution_count, item.policy_id),
    )
    exploit_count = max(1, min(limit, int(round(limit * exploit_ratio))))
    explore_count = max(0, limit - exploit_count)

    exploit = ranked[:exploit_count]
    remaining = [item for item in ranked[exploit_count:] if item not in exploit]
    explore = sorted(
        remaining,
        key=lambda item: (item.execution_count, item.confidence, item.policy_id),
    )[:explore_count]

    allocations: list[PolicyAllocation] = []
    for item in exploit:
        allocations.append(
            PolicyAllocation(
                policy_id=item.policy_id,
                campaign_id=item.campaign_id,
                industry=item.industry,
                mode='exploit',
                success_score=item.success_score,
                confidence=item.confidence,
            )
        )
    for item in explore:
        allocations.append(
            PolicyAllocation(
                policy_id=item.policy_id,
                campaign_id=item.campaign_id,
                industry=item.industry,
                mode='explore',
                success_score=item.success_score,
                confidence=item.confidence,
            )
        )
    return allocations

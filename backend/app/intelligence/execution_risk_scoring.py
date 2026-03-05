from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.recommendation_execution import RecommendationExecution


_BASE_RISK_BY_TYPE: dict[str, float] = {
    'create_content_brief': 0.25,
    'improve_internal_links': 0.45,
    'fix_missing_title': 0.35,
    'optimize_gbp_profile': 0.65,
    'publish_schema_markup': 0.55,
}


@dataclass(frozen=True)
class ExecutionRisk:
    risk_score: float
    risk_level: str
    scope_of_change: int
    historical_success_rate: float


def score_execution_risk(
    db: Session,
    *,
    campaign_id: str,
    execution_type: str,
    scope_of_change: int,
) -> ExecutionRisk:
    base = float(_BASE_RISK_BY_TYPE.get(execution_type, 0.5))
    scoped = max(1, int(scope_of_change))
    scope_component = min(1.0, scoped / 20.0)

    settled = (
        db.query(RecommendationExecution)
        .filter(
            RecommendationExecution.campaign_id == campaign_id,
            RecommendationExecution.execution_type == execution_type,
            RecommendationExecution.status.in_(['completed', 'failed']),
        )
        .all()
    )
    total_count = len(settled)
    success_count = sum(1 for row in settled if row.status == 'completed')
    historical_success_rate = (success_count / total_count) if total_count > 0 else 0.75

    failure_component = 1.0 - historical_success_rate
    risk_score = max(0.0, min(1.0, 0.5 * base + 0.25 * scope_component + 0.25 * failure_component))

    if risk_score < 0.35:
        risk_level = 'low'
    elif risk_score < 0.7:
        risk_level = 'medium'
    else:
        risk_level = 'high'

    return ExecutionRisk(
        risk_score=round(risk_score, 6),
        risk_level=risk_level,
        scope_of_change=scoped,
        historical_success_rate=round(historical_success_rate, 6),
    )

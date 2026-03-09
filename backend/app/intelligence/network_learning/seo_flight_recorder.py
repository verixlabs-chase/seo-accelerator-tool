from __future__ import annotations

from datetime import UTC, datetime
import json

from sqlalchemy.orm import Session

from app.models.execution_mutation import ExecutionMutation
from app.models.recommendation_execution import RecommendationExecution
from app.models.recommendation_outcome import RecommendationOutcome
from app.models.seo_mutation_outcome import SEOMutationOutcome


def record_seo_flight(
    db: Session,
    *,
    execution_id: str,
    industry_id: str | None = None,
    rank_before: float | None = None,
    rank_after: float | None = None,
    traffic_before: float | None = None,
    traffic_after: float | None = None,
    recorded_at: datetime | None = None,
) -> list[SEOMutationOutcome]:
    execution = db.get(RecommendationExecution, execution_id)
    if execution is None:
        return []
    outcome = (
        db.query(RecommendationOutcome)
        .filter(RecommendationOutcome.recommendation_id == execution.recommendation_id)
        .order_by(RecommendationOutcome.measured_at.desc(), RecommendationOutcome.id.desc())
        .first()
    )
    mutations = (
        db.query(ExecutionMutation)
        .filter(ExecutionMutation.execution_id == execution.id)
        .order_by(ExecutionMutation.created_at.asc(), ExecutionMutation.id.asc())
        .all()
    )
    if not mutations:
        return []

    rank_before_value = float(rank_before if rank_before is not None else (outcome.metric_before if outcome is not None else 0.0))
    rank_after_value = float(rank_after if rank_after is not None else (outcome.metric_after if outcome is not None else rank_before_value))
    traffic_before_value = float(traffic_before if traffic_before is not None else 0.0)
    traffic_after_value = float(traffic_after if traffic_after is not None else traffic_before_value)
    industry_key = _normalize_industry(industry_id)

    rows: list[SEOMutationOutcome] = []
    for mutation in mutations:
        row = SEOMutationOutcome(
            execution_id=execution.id,
            mutation_id=mutation.id,
            campaign_id=execution.campaign_id,
            industry_id=industry_key,
            page_url=mutation.target_url,
            mutation_type=mutation.mutation_type,
            mutation_parameters=_coerce_mutation_parameters(mutation.mutation_payload),
            rank_before=rank_before_value,
            rank_after=rank_after_value,
            traffic_before=traffic_before_value,
            traffic_after=traffic_after_value,
            measured_delta=rank_after_value - rank_before_value,
            recorded_at=recorded_at or (outcome.measured_at if outcome is not None else datetime.now(UTC)),
        )
        db.add(row)
        rows.append(row)
    db.flush()
    return rows


def _normalize_industry(industry_id: str | None) -> str:
    value = str(industry_id or 'unknown').strip().lower().replace(' ', '_')
    return value or 'unknown'


def _coerce_mutation_parameters(raw_payload: str | None) -> dict[str, object]:
    if not raw_payload:
        return {}
    try:
        parsed = json.loads(raw_payload)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}

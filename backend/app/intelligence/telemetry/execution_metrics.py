from __future__ import annotations

from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.execution_mutation import ExecutionMutation
from app.models.recommendation_execution import RecommendationExecution


def snapshot_execution_metrics(db: Session) -> dict[str, Any]:
    total = db.query(func.count(RecommendationExecution.id)).scalar() or 0
    completed = db.query(func.count(RecommendationExecution.id)).filter(RecommendationExecution.status == 'completed').scalar() or 0
    rolled_back = db.query(func.count(RecommendationExecution.id)).filter(RecommendationExecution.status == 'rolled_back').scalar() or 0
    mutation_total = db.query(func.count(ExecutionMutation.id)).scalar() or 0
    rollback_rate = 0.0 if mutation_total == 0 else round(float(rolled_back) / float(mutation_total), 6)
    success_rate = 0.0 if total == 0 else round(float(completed) / float(total), 6)
    return {
        'execution_total': int(total),
        'execution_success_rate': success_rate,
        'mutation_rollback_rate': rollback_rate,
    }

from __future__ import annotations

from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.recommendation_execution import RecommendationExecution
from app.models.recommendation_outcome import RecommendationOutcome
from app.models.temporal import TemporalSignalSnapshot


def snapshot_pipeline_metrics(db: Session) -> dict[str, Any]:
    signals = db.query(func.count(TemporalSignalSnapshot.id)).scalar() or 0
    executions = db.query(func.count(RecommendationExecution.id)).scalar() or 0
    outcomes = db.query(func.count(RecommendationOutcome.id)).scalar() or 0
    worker_throughput = 0.0 if signals == 0 else round(float(executions) / float(signals), 6)
    return {
        'signals_processed': int(signals),
        'executions_recorded': int(executions),
        'outcomes_recorded': int(outcomes),
        'worker_throughput': worker_throughput,
    }

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.intelligence.evolution.strategy_evolution_engine import process as process_strategy_evolution
from app.intelligence.telemetry.learning_metrics_engine import snapshot_learning_metrics_payload
from app.intelligence.telemetry.learning_reports import persist_learning_report


def process(db: Session, payload: dict[str, object]) -> dict[str, object]:
    result = process_strategy_evolution(db, payload)
    telemetry = snapshot_learning_metrics_payload(db)
    current = datetime.now(UTC)
    persist_learning_report(db, report_date=current.date(), now=current)
    result['learning_metrics'] = telemetry
    return result

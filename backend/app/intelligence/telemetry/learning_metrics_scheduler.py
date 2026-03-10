from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.intelligence.telemetry.learning_metrics_engine import snapshot_learning_metrics_payload
from app.intelligence.telemetry.learning_reports import persist_learning_report


def run_daily_learning_snapshot(db: Session, *, now: datetime | None = None) -> dict[str, Any]:
    current = now or datetime.now(UTC)
    snapshot = snapshot_learning_metrics_payload(db)
    report = persist_learning_report(db, report_date=current.date(), now=current)
    return {
        'schedule': 'daily',
        'timestamp': current.isoformat(),
        'snapshot': snapshot,
        'report_id': report.id,
        'report_date': report.report_date.isoformat(),
    }


def run_weekly_learning_snapshot(db: Session, *, now: datetime | None = None) -> dict[str, Any]:
    current = now or datetime.now(UTC)
    snapshot = snapshot_learning_metrics_payload(db)
    report = persist_learning_report(db, report_date=current.date(), now=current)
    return {
        'schedule': 'weekly',
        'timestamp': current.isoformat(),
        'snapshot': snapshot,
        'report_id': report.id,
        'report_date': report.report_date.isoformat(),
    }

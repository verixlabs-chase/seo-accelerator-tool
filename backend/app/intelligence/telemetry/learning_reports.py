from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.learning_metric_snapshot import LearningMetricSnapshot
from app.models.learning_report import LearningReport


REPORT_FIELDS = (
    'mutation_success_rate',
    'experiment_win_rate',
    'policy_improvement_velocity',
    'causal_confidence_mean',
)


def generate_learning_report(db: Session, *, now: datetime | None = None) -> dict[str, Any]:
    current = now or datetime.now(UTC)
    seven_day = _window_averages(db, current=current, days=7)
    thirty_day = _window_averages(db, current=current, days=30)
    trend = _trend_direction(seven_day=seven_day, thirty_day=thirty_day)
    return {
        'report_date': current.date().isoformat(),
        'seven_day_averages': seven_day,
        'thirty_day_averages': thirty_day,
        'trend_direction': trend,
    }


def persist_learning_report(db: Session, *, report_date: date | None = None, now: datetime | None = None) -> LearningReport:
    current = now or datetime.now(UTC)
    target_date = report_date or current.date()
    payload = generate_learning_report(db, now=current)
    seven_day = payload['seven_day_averages']
    row = (
        db.query(LearningReport)
        .filter(LearningReport.report_date == target_date)
        .first()
    )
    if row is None:
        row = LearningReport(report_date=target_date)
        db.add(row)
    row.mutation_success_rate = float(seven_day['mutation_success_rate'])
    row.experiment_win_rate = float(seven_day['experiment_win_rate'])
    row.policy_improvement_velocity = float(seven_day['policy_improvement_velocity'])
    row.causal_confidence_mean = float(seven_day['causal_confidence_mean'])
    row.trend = str(payload['trend_direction'])
    db.flush()
    return row


def _window_averages(db: Session, *, current: datetime, days: int) -> dict[str, float]:
    window_start = current - timedelta(days=max(1, days) - 1)
    row = (
        db.query(
            func.coalesce(func.avg(LearningMetricSnapshot.mutation_success_rate), 0.0),
            func.coalesce(func.avg(LearningMetricSnapshot.experiment_win_rate), 0.0),
            func.coalesce(func.avg(LearningMetricSnapshot.policy_improvement_velocity), 0.0),
            func.coalesce(func.avg(LearningMetricSnapshot.causal_confidence_mean), 0.0),
        )
        .filter(LearningMetricSnapshot.timestamp >= window_start)
        .first()
    )
    values = [round(float(item or 0.0), 6) for item in row]
    return dict(zip(REPORT_FIELDS, values, strict=False))


def _trend_direction(*, seven_day: dict[str, float], thirty_day: dict[str, float]) -> str:
    deltas = [float(seven_day[field]) - float(thirty_day[field]) for field in REPORT_FIELDS]
    score = sum(deltas)
    if score > 0.05:
        return 'up'
    if score < -0.05:
        return 'down'
    return 'stable'

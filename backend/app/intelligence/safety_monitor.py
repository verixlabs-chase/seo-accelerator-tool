from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.events import emit_event
from app.models.audit_log import AuditLog
from app.models.intelligence import AnomalyEvent
from app.models.recommendation_execution import RecommendationExecution
from app.models.recommendation_outcome import RecommendationOutcome
from app.models.strategy_cohort_pattern import StrategyCohortPattern

FAILURE_RATE_THRESHOLD = 0.6
NEGATIVE_OUTCOME_SPIKE_RATIO = 2.0
NEGATIVE_OUTCOME_MIN_COUNT = 3
PATTERN_INSTABILITY_GROWTH = 2.0


def evaluate_and_apply_safety_breaker(db: Session, *, tenant_id: str = 'system') -> dict[str, object]:
    now = datetime.now(UTC)
    start = now - timedelta(hours=24)
    prior_start = now - timedelta(hours=48)

    failed_count = (
        db.query(RecommendationExecution)
        .filter(
            RecommendationExecution.created_at >= start,
            RecommendationExecution.status == 'failed',
        )
        .count()
    )
    settled_count = (
        db.query(RecommendationExecution)
        .filter(
            RecommendationExecution.created_at >= start,
            RecommendationExecution.status.in_(['completed', 'failed']),
        )
        .count()
    )
    failure_rate = (failed_count / settled_count) if settled_count > 0 else 0.0

    negative_outcomes = (
        db.query(RecommendationOutcome)
        .filter(
            RecommendationOutcome.measured_at >= start,
            RecommendationOutcome.delta < 0,
        )
        .count()
    )
    positive_outcomes = (
        db.query(RecommendationOutcome)
        .filter(
            RecommendationOutcome.measured_at >= start,
            RecommendationOutcome.delta > 0,
        )
        .count()
    )
    outcome_ratio = negative_outcomes / max(positive_outcomes, 1)

    recent_patterns = (
        db.query(StrategyCohortPattern)
        .filter(StrategyCohortPattern.created_at >= start)
        .count()
    )
    prior_patterns = (
        db.query(StrategyCohortPattern)
        .filter(StrategyCohortPattern.created_at >= prior_start, StrategyCohortPattern.created_at < start)
        .count()
    )
    pattern_growth = recent_patterns / max(prior_patterns, 1)

    instability_events = (
        db.query(AnomalyEvent)
        .filter(AnomalyEvent.detected_at >= start, AnomalyEvent.anomaly_type == 'pattern_instability')
        .count()
    )

    reasons: list[str] = []
    if failure_rate > FAILURE_RATE_THRESHOLD:
        reasons.append('execution_failure_rate_exceeded')
    if negative_outcomes >= NEGATIVE_OUTCOME_MIN_COUNT and outcome_ratio > NEGATIVE_OUTCOME_SPIKE_RATIO:
        reasons.append('negative_outcomes_spike')
    if pattern_growth > PATTERN_INSTABILITY_GROWTH or instability_events > 0:
        reasons.append('pattern_detection_instability')

    triggered = len(reasons) > 0
    payload = {
        'triggered': triggered,
        'failure_rate': round(failure_rate, 6),
        'negative_outcomes': int(negative_outcomes),
        'positive_outcomes': int(positive_outcomes),
        'pattern_growth': round(pattern_growth, 6),
        'instability_events': int(instability_events),
        'reasons': reasons,
        'evaluated_at': now.isoformat(),
    }

    if triggered:
        if not is_safety_paused(db):
            emit_event(db, tenant_id=tenant_id, event_type='intelligence.safety_breaker.triggered', payload=payload)
            db.commit()
    return payload


def is_safety_paused(db: Session, *, now: datetime | None = None) -> bool:
    current = now or datetime.now(UTC)
    last_trigger = (
        db.query(AuditLog)
        .filter(AuditLog.event_type == 'intelligence.safety_breaker.triggered')
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .first()
    )
    if last_trigger is None:
        return False

    created_at = last_trigger.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    if current - created_at > timedelta(hours=24):
        return False

    payload = {}
    try:
        event = json.loads(last_trigger.payload_json)
        payload = dict(event.get('payload') or {})
    except Exception:
        payload = {}

    return bool(payload.get('triggered', True))

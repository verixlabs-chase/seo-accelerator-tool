from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.enums import StrategyRecommendationStatus
from app.events import emit_event
from app.intelligence.executors.registry import get_executor
from app.intelligence.outcome_tracker import record_execution_outcome
from app.intelligence.signal_assembler import assemble_signals
from app.models.intelligence import StrategyRecommendation
from app.models.recommendation_execution import RecommendationExecution

MAX_EXECUTIONS_PER_CAMPAIGN_PER_DAY = 20
RETRY_LIMIT = 3
TERMINAL_RECOMMENDATION_STATUSES = {
    StrategyRecommendationStatus.EXECUTED,
    StrategyRecommendationStatus.FAILED,
    StrategyRecommendationStatus.ROLLED_BACK,
    StrategyRecommendationStatus.ARCHIVED,
}

_EXECUTION_TYPE_MAP: dict[str, str] = {
    'content': 'create_content_brief',
    'internal': 'improve_internal_links',
    'title': 'fix_missing_title',
    'gbp': 'optimize_gbp_profile',
    'schema': 'publish_schema_markup',
}

_DEFAULT_METRIC_BY_EXECUTION_TYPE: dict[str, str] = {
    'create_content_brief': 'content_count',
    'improve_internal_links': 'avg_rank',
    'fix_missing_title': 'technical_issue_count',
    'optimize_gbp_profile': 'local_health',
    'publish_schema_markup': 'technical_issue_count',
}


def schedule_execution(recommendation_id: str, db: Session | None = None) -> RecommendationExecution | None:
    owns_session = db is None
    session = db or SessionLocal()
    try:
        recommendation = session.get(StrategyRecommendation, recommendation_id)
        if recommendation is None:
            return None
        if recommendation.status not in {StrategyRecommendationStatus.APPROVED, StrategyRecommendationStatus.SCHEDULED}:
            return None

        now = datetime.now(UTC)
        day_start = datetime(now.year, now.month, now.day, tzinfo=UTC)
        daily_count = (
            session.query(RecommendationExecution)
            .filter(
                RecommendationExecution.campaign_id == recommendation.campaign_id,
                RecommendationExecution.created_at >= day_start,
            )
            .count()
        )
        if daily_count >= MAX_EXECUTIONS_PER_CAMPAIGN_PER_DAY:
            return None

        execution_type = _execution_type_for(recommendation.recommendation_type)
        metric_name = _DEFAULT_METRIC_BY_EXECUTION_TYPE.get(execution_type, 'avg_rank')
        signals = assemble_signals(recommendation.campaign_id, db=session)
        metric_before = float(signals.get(metric_name, 0.0) or 0.0)
        idempotency_key = f'{recommendation.id}:{execution_type}:{day_start.date().isoformat()}'

        existing = session.query(RecommendationExecution).filter(RecommendationExecution.idempotency_key == idempotency_key).first()
        if existing is not None:
            return existing

        payload = {
            'recommendation_id': recommendation.id,
            'campaign_id': recommendation.campaign_id,
            'tenant_id': recommendation.tenant_id,
            'metric_name': metric_name,
            'metric_before': metric_before,
            'idempotency_key': idempotency_key,
        }

        execution = RecommendationExecution(
            recommendation_id=recommendation.id,
            campaign_id=recommendation.campaign_id,
            execution_type=execution_type,
            execution_payload=json.dumps(payload, sort_keys=True),
            idempotency_key=idempotency_key,
            deterministic_hash=_deterministic_hash(execution_type=execution_type, payload=payload),
            status='scheduled',
            attempt_count=0,
        )
        session.add(execution)
        _set_recommendation_status_if_allowed(recommendation, StrategyRecommendationStatus.SCHEDULED)
        session.flush()

        _emit_execution_event(session, recommendation.tenant_id, 'execution.scheduled', execution=execution, result_summary=None)
        if owns_session:
            session.commit()
            session.refresh(execution)
        return execution
    finally:
        if owns_session:
            session.close()


def execute_recommendation(
    execution_id: str,
    db: Session | None = None,
    *,
    dry_run: bool = False,
) -> RecommendationExecution | dict[str, Any] | None:
    owns_session = db is None
    session = db or SessionLocal()
    try:
        execution = session.get(RecommendationExecution, execution_id)
        if execution is None:
            return None
        if not dry_run and execution.status in {'running', 'completed'}:
            return execution

        payload = _load_payload(execution.execution_payload)
        executor = get_executor(execution.execution_type)
        executor.validate(payload)

        if dry_run:
            return _normalize_result(executor.plan(payload), execution.execution_type)

        if int(execution.attempt_count or 0) >= RETRY_LIMIT:
            execution.status = 'failed'
            execution.last_error = 'retry limit exceeded'
            failed = _failed_result(execution.execution_type, 'Retry limit exceeded before execution.')
            execution.result_summary = json.dumps(failed, sort_keys=True)
            recommendation = session.get(StrategyRecommendation, execution.recommendation_id)
            if recommendation is not None:
                _emit_execution_event(session, recommendation.tenant_id, 'execution.failed', execution=execution, result_summary=failed)
            if owns_session:
                session.commit()
            return execution

        execution.status = 'running'
        execution.attempt_count = int(execution.attempt_count or 0) + 1
        execution.last_error = None
        session.flush()

        recommendation = session.get(StrategyRecommendation, execution.recommendation_id)
        if recommendation is not None:
            _emit_execution_event(session, recommendation.tenant_id, 'execution.started', execution=execution, result_summary=None)

        try:
            result = _normalize_result(executor.run(payload), execution.execution_type)
        except Exception as exc:  # pragma: no cover
            result = _failed_result(execution.execution_type, str(exc))

        if result['status'] == 'failed':
            execution.status = 'failed'
            execution.last_error = result.get('notes', 'execution failed')
            execution.result_summary = json.dumps(result, sort_keys=True)
            execution.executed_at = datetime.now(UTC)
            if recommendation is not None:
                _set_recommendation_status_if_allowed(recommendation, StrategyRecommendationStatus.FAILED)
                _emit_execution_event(session, recommendation.tenant_id, 'execution.failed', execution=execution, result_summary=result)
            if owns_session:
                session.commit()
                session.refresh(execution)
            return execution

        execution.status = 'completed'
        execution.last_error = None
        execution.executed_at = datetime.now(UTC)
        execution.result_summary = json.dumps(result, sort_keys=True)

        if recommendation is not None:
            _set_recommendation_status_if_allowed(recommendation, StrategyRecommendationStatus.EXECUTED)
            _emit_execution_event(session, recommendation.tenant_id, 'execution.completed', execution=execution, result_summary=result)

        _record_outcome_if_possible(session, execution, result)

        if owns_session:
            session.commit()
            session.refresh(execution)
        return execution
    except Exception as exc:
        execution = session.get(RecommendationExecution, execution_id)
        if execution is not None:
            execution.status = 'failed'
            execution.last_error = str(exc)
            failed = _failed_result(execution.execution_type, str(exc))
            execution.result_summary = json.dumps(failed, sort_keys=True)
            execution.executed_at = datetime.now(UTC)
            recommendation = session.get(StrategyRecommendation, execution.recommendation_id)
            if recommendation is not None:
                _set_recommendation_status_if_allowed(recommendation, StrategyRecommendationStatus.FAILED)
                _emit_execution_event(session, recommendation.tenant_id, 'execution.failed', execution=execution, result_summary=failed)
            if owns_session:
                session.commit()
        return execution
    finally:
        if owns_session:
            session.close()


def record_execution_result(
    execution_id: str,
    result: dict[str, Any],
    db: Session | None = None,
) -> RecommendationExecution | None:
    owns_session = db is None
    session = db or SessionLocal()
    try:
        execution = session.get(RecommendationExecution, execution_id)
        if execution is None:
            return None

        normalized = _normalize_result(result, execution.execution_type)
        execution.status = normalized['status'] if normalized['status'] in {'completed', 'failed'} else 'completed'
        execution.result_summary = json.dumps(normalized, sort_keys=True)
        execution.executed_at = datetime.now(UTC)
        execution.last_error = normalized.get('notes') if execution.status == 'failed' else None

        recommendation = session.get(StrategyRecommendation, execution.recommendation_id)
        if recommendation is not None:
            target = StrategyRecommendationStatus.EXECUTED if execution.status == 'completed' else StrategyRecommendationStatus.FAILED
            _set_recommendation_status_if_allowed(recommendation, target)
            event_type = 'execution.completed' if execution.status == 'completed' else 'execution.failed'
            _emit_execution_event(session, recommendation.tenant_id, event_type, execution=execution, result_summary=normalized)

        _record_outcome_if_possible(session, execution, normalized)

        if owns_session:
            session.commit()
            session.refresh(execution)
        return execution
    finally:
        if owns_session:
            session.close()


def retry_execution(execution_id: str, db: Session | None = None) -> RecommendationExecution | None:
    owns_session = db is None
    session = db or SessionLocal()
    try:
        execution = session.get(RecommendationExecution, execution_id)
        if execution is None:
            return None
        if execution.status != 'failed':
            return execution
        if int(execution.attempt_count or 0) >= RETRY_LIMIT:
            return execution

        execution.status = 'scheduled'
        execution.last_error = None
        session.flush()

        recommendation = session.get(StrategyRecommendation, execution.recommendation_id)
        if recommendation is not None:
            _emit_execution_event(session, recommendation.tenant_id, 'execution.scheduled', execution=execution, result_summary=None)

        if owns_session:
            session.commit()
            session.refresh(execution)
        return execution
    finally:
        if owns_session:
            session.close()


def cancel_execution(execution_id: str, db: Session | None = None) -> RecommendationExecution | None:
    owns_session = db is None
    session = db or SessionLocal()
    try:
        execution = session.get(RecommendationExecution, execution_id)
        if execution is None:
            return None
        if execution.status not in {'pending', 'scheduled'}:
            return execution

        execution.status = 'failed'
        execution.last_error = 'cancelled'
        failed = _failed_result(execution.execution_type, 'Cancelled before execution.')
        execution.result_summary = json.dumps(failed, sort_keys=True)
        execution.executed_at = datetime.now(UTC)

        recommendation = session.get(StrategyRecommendation, execution.recommendation_id)
        if recommendation is not None:
            _set_recommendation_status_if_allowed(recommendation, StrategyRecommendationStatus.FAILED)
            _emit_execution_event(session, recommendation.tenant_id, 'execution.failed', execution=execution, result_summary=failed)

        if owns_session:
            session.commit()
            session.refresh(execution)
        return execution
    finally:
        if owns_session:
            session.close()


def _execution_type_for(recommendation_type: str) -> str:
    lowered = recommendation_type.lower()
    for token, execution_type in _EXECUTION_TYPE_MAP.items():
        if token in lowered:
            return execution_type
    return 'create_content_brief'


def _set_recommendation_status_if_allowed(recommendation: StrategyRecommendation, target: StrategyRecommendationStatus) -> None:
    current = recommendation.status
    if current in TERMINAL_RECOMMENDATION_STATUSES and current != target:
        return
    recommendation.status = target


def _record_outcome_if_possible(session: Session, execution: RecommendationExecution, result: dict[str, Any]) -> None:
    if execution.status != 'completed':
        return

    payload = _load_payload(execution.execution_payload)
    metric_before_value = result.get('metric_before')
    if metric_before_value is not None:
        metric_before = float(metric_before_value)
    else:
        metric_before = float(payload.get('metric_before', 0.0) or 0.0)

    metric_after_value = result.get('metric_after')
    if metric_after_value is not None:
        metric_after = float(metric_after_value)
    else:
        metric_name = str(payload.get('metric_name', '') or '')
        signals = assemble_signals(execution.campaign_id, db=session)
        metric_after = float(signals.get(metric_name, metric_before) or metric_before)

    record_execution_outcome(
        session,
        execution=execution,
        metric_before=metric_before,
        metric_after=metric_after,
    )


def _normalize_result(result: dict[str, Any], execution_type: str) -> dict[str, Any]:
    actions = result.get('actions', [])
    if not isinstance(actions, list):
        actions = [str(actions)]

    artifacts = result.get('artifacts', {})
    if not isinstance(artifacts, dict):
        artifacts = {'value': str(artifacts)}

    metrics = result.get('metrics_to_measure', [])
    if not isinstance(metrics, list):
        metrics = [str(metrics)]

    status = str(result.get('status', 'completed')).lower()
    if status not in {'planned', 'completed', 'failed'}:
        status = 'completed'

    normalized = {
        'execution_type': execution_type,
        'status': status,
        'actions': [str(item) for item in actions],
        'artifacts': {str(key): value for key, value in artifacts.items()},
        'metrics_to_measure': [str(item) for item in metrics],
        'notes': str(result.get('notes', '')),
    }

    for optional_key in ('metric_name', 'metric_before', 'metric_after', 'delta'):
        if optional_key in result:
            normalized[optional_key] = result[optional_key]

    return normalized


def _failed_result(execution_type: str, note: str) -> dict[str, Any]:
    return {
        'execution_type': execution_type,
        'status': 'failed',
        'actions': [],
        'artifacts': {},
        'metrics_to_measure': [],
        'notes': note,
    }


def _load_payload(payload: str | None) -> dict[str, Any]:
    if not payload:
        return {}
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _deterministic_hash(*, execution_type: str, payload: dict[str, Any]) -> str:
    canonical = json.dumps({'execution_type': execution_type, 'payload': payload}, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def _emit_execution_event(
    db: Session,
    tenant_id: str,
    event_type: str,
    *,
    execution: RecommendationExecution,
    result_summary: dict[str, Any] | None,
) -> None:
    payload = {
        'execution_id': execution.id,
        'recommendation_id': execution.recommendation_id,
        'campaign_id': execution.campaign_id,
        'execution_type': execution.execution_type,
        'idempotency_key': execution.idempotency_key,
        'deterministic_hash': execution.deterministic_hash,
        'status': execution.status,
        'attempt_count': int(execution.attempt_count or 0),
        'created_at': execution.created_at.isoformat() if execution.created_at else None,
        'executed_at': execution.executed_at.isoformat() if execution.executed_at else None,
        'event_recorded_at': datetime.now(UTC).isoformat(),
        'result_summary': result_summary or {},
    }
    emit_event(db, tenant_id=tenant_id, event_type=event_type, payload=payload)

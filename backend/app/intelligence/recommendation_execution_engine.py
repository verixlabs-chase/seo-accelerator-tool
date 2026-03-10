from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.enums import StrategyRecommendationStatus
from app.events.emitter import outbox_event_write
from app.intelligence.execution_risk_scoring import score_execution_risk
from app.intelligence.executors.registry import get_executor
from app.intelligence.executors.wordpress_plugin import WordPressExecutionError, apply_mutations, rollback_mutations
from app.intelligence.outcome_tracker import record_execution_outcome
from app.intelligence.safety_monitor import is_safety_paused
from app.intelligence.signal_assembler import assemble_signals
from app.models.campaign import Campaign
from app.models.execution_mutation import ExecutionMutation
from app.models.intelligence import StrategyRecommendation
from app.models.intelligence_governance_policy import IntelligenceGovernancePolicy
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


def schedule_execution(recommendation_id: str, db: Session | None = None) -> RecommendationExecution | dict[str, Any] | None:
    owns_session = db is None
    session = db or SessionLocal()
    try:
        recommendation = session.get(StrategyRecommendation, recommendation_id)
        if recommendation is None:
            return None
        if recommendation.status not in {StrategyRecommendationStatus.APPROVED, StrategyRecommendationStatus.SCHEDULED}:
            return None
        campaign = session.get(Campaign, recommendation.campaign_id)
        if campaign is None:
            return None
        if is_safety_paused(session):
            return _governance_block(campaign_id=recommendation.campaign_id, execution_type='unknown', reason_code='safety_circuit_breaker_active', message='Safety circuit breaker is active. Scheduling is paused.')
        now = datetime.now(UTC)
        day_start = datetime(now.year, now.month, now.day, tzinfo=UTC)
        execution_type = _execution_type_for(recommendation.recommendation_type)
        policy = _resolve_governance_policy(session, campaign_id=recommendation.campaign_id, execution_type=execution_type)
        if not policy['enabled']:
            return _governance_block(campaign_id=recommendation.campaign_id, execution_type=execution_type, reason_code='execution_type_disabled', message='Execution type is disabled by governance policy.')
        daily_count = (
            session.query(RecommendationExecution)
            .filter(RecommendationExecution.campaign_id == recommendation.campaign_id, RecommendationExecution.execution_type == execution_type, RecommendationExecution.created_at >= day_start)
            .count()
        )
        daily_cap = min(int(policy['max_daily_executions']), MAX_EXECUTIONS_PER_CAMPAIGN_PER_DAY)
        if daily_count >= daily_cap:
            return _governance_block(campaign_id=recommendation.campaign_id, execution_type=execution_type, reason_code='max_daily_executions_exceeded', message='Daily execution cap exceeded by governance policy.')
        metric_name = _DEFAULT_METRIC_BY_EXECUTION_TYPE.get(execution_type, 'avg_rank')
        signals = assemble_signals(recommendation.campaign_id, db=session)
        metric_before = float(signals.get(metric_name, 0.0) or 0.0)
        idempotency_key = f'{recommendation.id}:{execution_type}:{day_start.date().isoformat()}'
        existing = session.query(RecommendationExecution).filter(RecommendationExecution.idempotency_key == idempotency_key).first()
        if existing is not None:
            return existing
        scope_of_change = max(1, int((recommendation.risk_tier or 1) * 2))
        risk = score_execution_risk(session, campaign_id=recommendation.campaign_id, execution_type=execution_type, scope_of_change=scope_of_change)
        payload = _build_execution_payload(recommendation=recommendation, campaign=campaign, metric_name=metric_name, metric_before=metric_before, idempotency_key=idempotency_key, requires_manual_approval=bool(policy['requires_manual_approval']))
        initial_status = 'pending' if policy['requires_manual_approval'] else 'scheduled'
        execution = RecommendationExecution(
            recommendation_id=recommendation.id,
            campaign_id=recommendation.campaign_id,
            execution_type=execution_type,
            execution_payload=json.dumps(payload, sort_keys=True),
            idempotency_key=idempotency_key,
            deterministic_hash=_deterministic_hash(execution_type=execution_type, payload=payload),
            status=initial_status,
            attempt_count=0,
            risk_score=risk.risk_score,
            risk_level=risk.risk_level,
            scope_of_change=risk.scope_of_change,
            historical_success_rate=risk.historical_success_rate,
        )
        if policy['requires_manual_approval']:
            execution.result_summary = json.dumps(_governance_block(campaign_id=recommendation.campaign_id, execution_type=execution_type, reason_code='manual_approval_required', message='Execution requires manual approval before run.'), sort_keys=True)
        session.add(execution)
        if initial_status == 'scheduled':
            _set_recommendation_status_if_allowed(recommendation, StrategyRecommendationStatus.SCHEDULED)
        session.flush()
        outbox_event_write(session, tenant_id=recommendation.tenant_id, event_type='execution.scheduled', payload=_execution_event_payload(execution=execution, result_summary=None))
        if owns_session:
            session.commit()
            session.refresh(execution)
        return execution
    finally:
        if owns_session:
            session.close()


def execute_recommendation(execution_id: str, db: Session | None = None, *, dry_run: bool = False) -> RecommendationExecution | dict[str, Any] | None:
    owns_session = db is None
    session = db or SessionLocal()
    try:
        execution = session.get(RecommendationExecution, execution_id)
        if execution is None:
            return None
        if not dry_run and execution.status in {'running', 'completed', 'rolled_back'}:
            return execution
        payload = _load_payload(execution.execution_payload)
        executor = get_executor(execution.execution_type)
        executor.validate(payload)
        if dry_run:
            return _normalize_result(executor.plan(payload), execution.execution_type)
        recommendation = session.get(StrategyRecommendation, execution.recommendation_id)
        if recommendation is None:
            return None
        if is_safety_paused(session):
            execution.last_error = 'safety_circuit_breaker_active'
            execution.result_summary = json.dumps(_governance_block(campaign_id=execution.campaign_id, execution_type=execution.execution_type, reason_code='safety_circuit_breaker_active', message='Safety circuit breaker is active. Execution blocked.'), sort_keys=True)
            if owns_session:
                session.commit()
            return execution
        policy = _resolve_governance_policy(session, campaign_id=execution.campaign_id, execution_type=execution.execution_type)
        if not policy['enabled']:
            execution.status = 'failed'
            execution.last_error = 'execution_type_disabled'
            execution.result_summary = json.dumps(_governance_block(campaign_id=execution.campaign_id, execution_type=execution.execution_type, reason_code='execution_type_disabled', message='Execution type disabled by governance policy.'), sort_keys=True)
            if owns_session:
                session.commit()
            return execution
        if policy['requires_manual_approval'] and not (execution.approved_by and execution.approved_at):
            execution.status = 'pending'
            execution.last_error = 'manual_approval_required'
            execution.result_summary = json.dumps(_governance_block(campaign_id=execution.campaign_id, execution_type=execution.execution_type, reason_code='manual_approval_required', message='Execution requires approval before run.'), sort_keys=True)
            if owns_session:
                session.commit()
            return execution
        if int(execution.attempt_count or 0) >= RETRY_LIMIT:
            execution.status = 'failed'
            execution.last_error = 'retry limit exceeded'
            failed = _failed_result(execution.execution_type, 'Retry limit exceeded before execution.')
            execution.result_summary = json.dumps(failed, sort_keys=True)
            outbox_event_write(session, tenant_id=recommendation.tenant_id, event_type='execution.failed', payload=_execution_event_payload(execution=execution, result_summary=failed))
            if owns_session:
                session.commit()
            return execution
        execution.status = 'running'
        execution.attempt_count = int(execution.attempt_count or 0) + 1
        execution.last_error = None
        session.flush()
        outbox_event_write(session, tenant_id=recommendation.tenant_id, event_type='execution.started', payload=_execution_event_payload(execution=execution, result_summary=None))
        try:
            result = _normalize_result(executor.run(payload), execution.execution_type)
            result = _deliver_mutations(session, execution=execution, result=result)
        except Exception as exc:  # pragma: no cover
            result = _failed_result(execution.execution_type, str(exc))
        if result['status'] == 'failed':
            execution.status = 'failed'
            execution.last_error = result.get('notes', 'execution failed')
            execution.result_summary = json.dumps(result, sort_keys=True)
            execution.executed_at = datetime.now(UTC)
            _set_recommendation_status_if_allowed(recommendation, StrategyRecommendationStatus.FAILED)
            outbox_event_write(session, tenant_id=recommendation.tenant_id, event_type='execution.failed', payload=_execution_event_payload(execution=execution, result_summary=result))
            if owns_session:
                session.commit()
                session.refresh(execution)
            return execution
        execution.status = 'completed'
        execution.last_error = None
        execution.executed_at = datetime.now(UTC)
        execution.result_summary = json.dumps(result, sort_keys=True)
        _set_recommendation_status_if_allowed(recommendation, StrategyRecommendationStatus.EXECUTED)
        outbox_event_write(session, tenant_id=recommendation.tenant_id, event_type='execution.completed', payload=_execution_event_payload(execution=execution, result_summary=result))
        _record_outcome_if_possible(session, execution, result)
        if owns_session:
            session.commit()
            session.refresh(execution)
        return execution
    finally:
        if owns_session:
            session.close()


def rollback_execution(execution_id: str, *, requested_by: str, db: Session | None = None) -> RecommendationExecution | None:
    owns_session = db is None
    session = db or SessionLocal()
    try:
        execution = session.get(RecommendationExecution, execution_id)
        if execution is None:
            return None
        if execution.status == 'rolled_back':
            return execution
        if execution.status != 'completed':
            return execution
        recommendation = session.get(StrategyRecommendation, execution.recommendation_id)
        if recommendation is None:
            return None
        mutations = (
            session.query(ExecutionMutation)
            .filter(ExecutionMutation.execution_id == execution.id, ExecutionMutation.status == 'applied')
            .order_by(ExecutionMutation.created_at.asc(), ExecutionMutation.id.asc())
            .all()
        )
        if not mutations:
            return execution
        try:
            delivery = rollback_mutations(session, execution=execution, mutation_rows=mutations)
        except (WordPressExecutionError, Exception) as exc:
            execution.last_error = str(exc)
            if owns_session:
                session.commit()
            return execution
        now = datetime.now(UTC)
        rollback_results = delivery.get('results', []) if isinstance(delivery.get('results'), list) else []
        for row in mutations:
            row.status = 'rolled_back'
            row.rolled_back_at = now
        execution.status = 'rolled_back'
        execution.rolled_back_at = now
        execution.last_error = None
        execution.result_summary = json.dumps({
            'execution_type': execution.execution_type,
            'status': 'rolled_back',
            'requested_by': requested_by,
            'rollback_delivery_mode': delivery.get('delivery_mode', 'unknown'),
            'rolled_back_mutations': rollback_results,
            'notes': 'Execution rollback completed using persisted mutation snapshots.',
            'mutations': [],
        }, sort_keys=True)
        recommendation.status = StrategyRecommendationStatus.ROLLED_BACK
        outbox_event_write(session, tenant_id=recommendation.tenant_id, event_type='execution.rolled_back', payload=_execution_event_payload(execution=execution, result_summary={'requested_by': requested_by, 'rolled_back_mutations': rollback_results}))
        if owns_session:
            session.commit()
            session.refresh(execution)
        return execution
    finally:
        if owns_session:
            session.close()


def approve_execution(execution_id: str, *, approved_by: str, db: Session | None = None) -> RecommendationExecution | None:
    owns_session = db is None
    session = db or SessionLocal()
    try:
        execution = session.get(RecommendationExecution, execution_id)
        if execution is None:
            return None
        execution.approved_by = approved_by
        execution.approved_at = datetime.now(UTC)
        if execution.status == 'pending':
            execution.status = 'scheduled'
        if owns_session:
            session.commit()
            session.refresh(execution)
        return execution
    finally:
        if owns_session:
            session.close()


def reject_execution(execution_id: str, *, rejected_by: str, db: Session | None = None) -> RecommendationExecution | None:
    owns_session = db is None
    session = db or SessionLocal()
    try:
        execution = session.get(RecommendationExecution, execution_id)
        if execution is None:
            return None
        execution.status = 'failed'
        execution.last_error = 'manual_rejection'
        execution.result_summary = json.dumps({'execution_type': execution.execution_type, 'status': 'failed', 'actions': [], 'artifacts': {}, 'metrics_to_measure': [], 'notes': f'rejected_by:{rejected_by}', 'reason_code': 'manual_rejection', 'mutations': []}, sort_keys=True)
        execution.executed_at = datetime.now(UTC)
        if owns_session:
            session.commit()
            session.refresh(execution)
        return execution
    finally:
        if owns_session:
            session.close()


def record_execution_result(execution_id: str, result: dict[str, Any], db: Session | None = None) -> RecommendationExecution | None:
    owns_session = db is None
    session = db or SessionLocal()
    try:
        execution = session.get(RecommendationExecution, execution_id)
        if execution is None:
            return None
        normalized = _normalize_result(result, execution.execution_type)
        execution.status = normalized['status'] if normalized['status'] in {'completed', 'failed', 'rolled_back'} else 'completed'
        execution.result_summary = json.dumps(normalized, sort_keys=True)
        execution.executed_at = datetime.now(UTC)
        execution.last_error = normalized.get('notes') if execution.status == 'failed' else None
        recommendation = session.get(StrategyRecommendation, execution.recommendation_id)
        if recommendation is not None:
            target = StrategyRecommendationStatus.EXECUTED if execution.status == 'completed' else StrategyRecommendationStatus.FAILED
            _set_recommendation_status_if_allowed(recommendation, target)
            event_type = 'execution.completed' if execution.status == 'completed' else 'execution.failed'
            outbox_event_write(session, tenant_id=recommendation.tenant_id, event_type=event_type, payload=_execution_event_payload(execution=execution, result_summary=normalized))
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
            outbox_event_write(session, tenant_id=recommendation.tenant_id, event_type='execution.scheduled', payload=_execution_event_payload(execution=execution, result_summary=None))
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
            outbox_event_write(session, tenant_id=recommendation.tenant_id, event_type='execution.failed', payload=_execution_event_payload(execution=execution, result_summary=failed))
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


def _resolve_governance_policy(db: Session, *, campaign_id: str, execution_type: str) -> dict[str, Any]:
    campaign_policy = (
        db.query(IntelligenceGovernancePolicy)
        .filter(IntelligenceGovernancePolicy.campaign_id == campaign_id, IntelligenceGovernancePolicy.execution_type == execution_type)
        .order_by(IntelligenceGovernancePolicy.updated_at.desc(), IntelligenceGovernancePolicy.id.desc())
        .first()
    )
    global_policy = (
        db.query(IntelligenceGovernancePolicy)
        .filter(IntelligenceGovernancePolicy.campaign_id.is_(None), IntelligenceGovernancePolicy.execution_type == execution_type)
        .order_by(IntelligenceGovernancePolicy.updated_at.desc(), IntelligenceGovernancePolicy.id.desc())
        .first()
    )
    policy = campaign_policy or global_policy
    if policy is None:
        return {'enabled': True, 'max_daily_executions': MAX_EXECUTIONS_PER_CAMPAIGN_PER_DAY, 'requires_manual_approval': False, 'risk_level': 'medium'}
    return {'enabled': bool(policy.enabled), 'max_daily_executions': int(policy.max_daily_executions), 'requires_manual_approval': bool(policy.requires_manual_approval), 'risk_level': str(policy.risk_level)}


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
    metric_before = float(metric_before_value) if metric_before_value is not None else float(payload.get('metric_before', 0.0) or 0.0)
    metric_after_value = result.get('metric_after')
    if metric_after_value is not None:
        metric_after = float(metric_after_value)
    else:
        metric_name = str(payload.get('metric_name', '') or '')
        signals = assemble_signals(execution.campaign_id, db=session)
        metric_after = float(signals.get(metric_name, metric_before) or metric_before)
    record_execution_outcome(session, execution=execution, metric_before=metric_before, metric_after=metric_after)


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
    if status not in {'planned', 'completed', 'failed', 'rolled_back'}:
        status = 'completed'
    mutations = result.get('mutations', [])
    if not isinstance(mutations, list):
        mutations = []
    normalized = {
        'execution_type': execution_type,
        'status': status,
        'actions': [str(item) for item in actions],
        'artifacts': {str(key): value for key, value in artifacts.items()},
        'metrics_to_measure': [str(item) for item in metrics],
        'notes': str(result.get('notes', '')),
        'mutations': mutations,
    }
    for optional_key in ('metric_name', 'metric_before', 'metric_after', 'delta', 'delivery_mode', 'provider_name', 'mutation_results', 'rollback_delivery_mode', 'rolled_back_mutations'):
        if optional_key in result:
            normalized[optional_key] = result[optional_key]
    return normalized


def _failed_result(execution_type: str, note: str) -> dict[str, Any]:
    return {'execution_type': execution_type, 'status': 'failed', 'actions': [], 'artifacts': {}, 'metrics_to_measure': [], 'notes': note, 'mutations': []}


def _governance_block(*, campaign_id: str, execution_type: str, reason_code: str, message: str) -> dict[str, Any]:
    return {'campaign_id': campaign_id, 'execution_type': execution_type, 'status': 'blocked', 'reason_code': reason_code, 'message': message}


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


def _execution_event_payload(*, execution: RecommendationExecution, result_summary: dict[str, Any] | None) -> dict[str, Any]:
    return {
        'execution_id': execution.id,
        'recommendation_id': execution.recommendation_id,
        'campaign_id': execution.campaign_id,
        'execution_type': execution.execution_type,
        'idempotency_key': execution.idempotency_key,
        'deterministic_hash': execution.deterministic_hash,
        'status': execution.status,
        'attempt_count': int(execution.attempt_count or 0),
        'approved_by': execution.approved_by,
        'approved_at': execution.approved_at.isoformat() if execution.approved_at else None,
        'risk_score': execution.risk_score,
        'risk_level': execution.risk_level,
        'scope_of_change': execution.scope_of_change,
        'historical_success_rate': execution.historical_success_rate,
        'created_at': execution.created_at.isoformat() if execution.created_at else None,
        'executed_at': execution.executed_at.isoformat() if execution.executed_at else None,
        'rolled_back_at': execution.rolled_back_at.isoformat() if execution.rolled_back_at else None,
        'event_recorded_at': datetime.now(UTC).isoformat(),
        'result_summary': result_summary or {},
    }


def _build_execution_payload(*, recommendation: StrategyRecommendation, campaign: Campaign, metric_name: str, metric_before: float, idempotency_key: str, requires_manual_approval: bool) -> dict[str, Any]:
    evidence = _load_payload(recommendation.evidence_json)
    rollback_plan = _load_payload(recommendation.rollback_plan_json)
    payload = {
        'recommendation_id': recommendation.id,
        'campaign_id': recommendation.campaign_id,
        'tenant_id': recommendation.tenant_id,
        'organization_id': campaign.organization_id,
        'campaign_name': campaign.name,
        'campaign_domain': campaign.domain,
        'recommendation_type': recommendation.recommendation_type,
        'recommendation_rationale': recommendation.rationale,
        'metric_name': metric_name,
        'metric_before': metric_before,
        'idempotency_key': idempotency_key,
        'requires_manual_approval': requires_manual_approval,
        'recommendation_context': evidence,
        'rollback_plan': rollback_plan,
    }
    if isinstance(evidence, dict):
        for key in ('source_url', 'target_url', 'anchor_text', 'schema_type', 'content_title', 'content_slug', 'content_target_url', 'meta_title', 'meta_description'):
            if key in evidence and evidence[key] is not None:
                payload[key] = evidence[key]
    return payload


def _deliver_mutations(session: Session, *, execution: RecommendationExecution, result: dict[str, Any]) -> dict[str, Any]:
    mutations = result.get('mutations', [])
    if not mutations:
        return result
    try:
        delivery = apply_mutations(session, execution=execution, mutations=mutations)
    except WordPressExecutionError as exc:
        failed = _failed_result(execution.execution_type, str(exc))
        failed['mutations'] = mutations
        return failed
    persisted = _persist_mutation_audit_rows(session, execution=execution, delivery=delivery, mutations=mutations)
    result['provider_name'] = delivery.get('provider_name', 'wordpress_plugin')
    result['delivery_mode'] = delivery.get('delivery_mode', 'unknown')
    result['mutation_results'] = persisted
    result['notes'] = f"{result.get('notes', '').strip()} Mutation delivery completed.".strip()
    return result


def _persist_mutation_audit_rows(session: Session, *, execution: RecommendationExecution, delivery: dict[str, Any], mutations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    now = datetime.now(UTC)
    results = delivery.get('results', []) if isinstance(delivery.get('results'), list) else []
    by_id = {str(item.get('mutation_id') or ''): item for item in results if isinstance(item, dict)}
    rows: list[dict[str, Any]] = []
    for mutation in mutations:
        result = by_id.get(str(mutation.get('mutation_id') or ''), {})
        row = ExecutionMutation(
            execution_id=execution.id,
            recommendation_id=execution.recommendation_id,
            campaign_id=execution.campaign_id,
            provider_name=str(delivery.get('provider_name', 'wordpress_plugin') or 'wordpress_plugin'),
            mutation_type=str(mutation.get('action', '') or ''),
            target_url=str(mutation.get('target_url', '/') or '/'),
            external_mutation_id=str(result.get('mutation_id') or mutation.get('mutation_id') or ''),
            mutation_payload=json.dumps(mutation, sort_keys=True),
            before_state=json.dumps(result.get('before_state', {}), sort_keys=True),
            after_state=json.dumps(result.get('after_state', {}), sort_keys=True),
            rollback_payload=json.dumps(result.get('rollback_payload', {}), sort_keys=True),
            status='applied',
            applied_at=now,
        )
        session.add(row)
        rows.append({'mutation_id': row.external_mutation_id, 'mutation_type': row.mutation_type, 'target_url': row.target_url, 'status': row.status})
    session.flush()
    return rows

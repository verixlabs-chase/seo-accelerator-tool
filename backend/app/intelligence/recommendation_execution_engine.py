from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
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
from app.models.wordpress_change_preview import WordPressChangePreview
from app.services.commercial_plan_service import (
    FEATURE_WORDPRESS_EXECUTION,
    require_commercial_feature,
)
from app.services.cost_economics_service import CostEconomicsError
from app.services.wordpress_change_preview_service import (
    WORDPRESS_MUTATION_EXECUTION_TYPES,
    WordPressChangePreviewError,
    approve_change_preview,
    bind_approved_preview,
    create_change_preview,
    requires_wordpress_preview,
)
from app.services.wordpress_post_change_measurement_service import (
    prepare_managed_wordpress_measurement,
    schedule_managed_wordpress_follow_up,
)
from app.services.wordpress_automation_policy_service import (
    evaluate_wordpress_automation,
    is_managed_wordpress_execution,
    pause_wordpress_automation_policy,
)

MAX_EXECUTIONS_PER_CAMPAIGN_PER_DAY = 20
RETRY_LIMIT = 3
logger = logging.getLogger("lsos.intelligence.execution")
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


def schedule_execution(
    recommendation_id: str,
    db: Session | None = None,
    *,
    managed_automation: bool = False,
    force_manual_approval: bool = False,
) -> RecommendationExecution | dict[str, Any] | None:
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
        automation_decision = None
        if managed_automation and execution_type in WORDPRESS_MUTATION_EXECUTION_TYPES:
            automation_decision = evaluate_wordpress_automation(
                session,
                campaign_id=recommendation.campaign_id,
                execution_type=execution_type,
                risk_tier=int(recommendation.risk_tier or 1),
                lock_policy=True,
                at=now,
            )
            if not automation_decision.allowed:
                return _governance_block(
                    campaign_id=recommendation.campaign_id,
                    execution_type=execution_type,
                    reason_code=automation_decision.reason_code,
                    message=automation_decision.message,
                )
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
        if managed_automation:
            idempotency_key = f'{idempotency_key}:managed'
        existing = session.query(RecommendationExecution).filter(RecommendationExecution.idempotency_key == idempotency_key).first()
        if existing is not None:
            return existing
        scope_of_change = max(1, int((recommendation.risk_tier or 1) * 2))
        risk = score_execution_risk(session, campaign_id=recommendation.campaign_id, execution_type=execution_type, scope_of_change=scope_of_change)
        requires_manual_approval = bool(force_manual_approval) or bool(policy['requires_manual_approval']) or bool(
            automation_decision and automation_decision.requires_manual_approval
        )
        payload = _build_execution_payload(
            recommendation=recommendation,
            campaign=campaign,
            metric_name=metric_name,
            metric_before=metric_before,
            idempotency_key=idempotency_key,
            requires_manual_approval=requires_manual_approval,
            managed_wordpress_automation=bool(
                managed_automation and execution_type in WORDPRESS_MUTATION_EXECUTION_TYPES
            ),
            automation_policy_version=(
                automation_decision.policy_version if automation_decision else None
            ),
        )
        initial_status = 'pending' if requires_manual_approval else 'scheduled'
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
        if requires_manual_approval:
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
            planned = _normalize_result(executor.plan(payload), execution.execution_type)
            if requires_wordpress_preview(execution):
                planned = create_change_preview(session, execution=execution, planned_result=planned)
            session.flush()
            return planned
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
        if is_managed_wordpress_execution(execution):
            automation_decision = evaluate_wordpress_automation(
                session,
                campaign_id=execution.campaign_id,
                execution_type=execution.execution_type,
                risk_tier=int(recommendation.risk_tier or 1),
                exclude_execution_id=execution.id,
            )
            if not automation_decision.allowed:
                execution.status = 'pending'
                execution.last_error = automation_decision.reason_code
                execution.result_summary = json.dumps(
                    _governance_block(
                        campaign_id=execution.campaign_id,
                        execution_type=execution.execution_type,
                        reason_code=automation_decision.reason_code,
                        message=automation_decision.message,
                    ),
                    sort_keys=True,
                )
                if owns_session:
                    session.commit()
                return execution
            if (
                not automation_decision.requires_manual_approval
                and not policy['requires_manual_approval']
                and not (execution.approved_by and execution.approved_at)
            ):
                try:
                    planned = _normalize_result(
                        executor.plan(payload),
                        execution.execution_type,
                    )
                    planned = create_change_preview(
                        session,
                        execution=execution,
                        planned_result=planned,
                    )
                    preview_payload = planned.get('preview')
                    if not isinstance(preview_payload, dict):
                        raise WordPressChangePreviewError(
                            'The managed update did not produce an exact website preview.',
                            reason_code='wordpress_preview_missing',
                        )
                    if preview_payload.get('status') != 'ready':
                        validation = preview_payload.get('managed_content_validation')
                        validation_blocked = (
                            isinstance(validation, dict)
                            and validation.get('status') == 'blocked'
                        )
                        raise WordPressChangePreviewError(
                            (
                                'The managed update did not pass its content and business-fact checks.'
                                if validation_blocked
                                else 'The managed update preview found a conflict that needs review.'
                            ),
                            reason_code=(
                                'wordpress_content_validation_failed'
                                if validation_blocked
                                else 'wordpress_preview_conflict'
                            ),
                        )
                    affected_urls = [
                        str(value)
                        for value in (preview_payload.get('affected_urls') or [])
                        if str(value).strip()
                    ]
                    scoped_decision = evaluate_wordpress_automation(
                        session,
                        campaign_id=execution.campaign_id,
                        execution_type=execution.execution_type,
                        risk_tier=int(recommendation.risk_tier or 1),
                        affected_urls=affected_urls,
                        exclude_execution_id=execution.id,
                    )
                    if not scoped_decision.allowed:
                        execution.status = 'pending'
                        execution.last_error = scoped_decision.reason_code
                        execution.result_summary = json.dumps(
                            _governance_block(
                                campaign_id=execution.campaign_id,
                                execution_type=execution.execution_type,
                                reason_code=scoped_decision.reason_code,
                                message=scoped_decision.message,
                            ),
                            sort_keys=True,
                        )
                        if owns_session:
                            session.commit()
                        return execution
                    approval_actor = (
                        f'InsightOS policy v{scoped_decision.policy_version or "unknown"}'
                    )
                    approve_change_preview(
                        session,
                        execution=execution,
                        preview_hash=str(preview_payload.get('preview_hash') or ''),
                        approved_by=approval_actor,
                    )
                    execution.approved_by = approval_actor
                    execution.approved_at = datetime.now(UTC)
                    execution.status = 'scheduled'
                    execution.last_error = None
                    session.flush()
                except WordPressChangePreviewError as exc:
                    execution.status = 'pending'
                    execution.last_error = exc.reason_code
                    execution.result_summary = json.dumps(
                        _governance_block(
                            campaign_id=execution.campaign_id,
                            execution_type=execution.execution_type,
                            reason_code=exc.reason_code,
                            message=str(exc),
                        ),
                        sort_keys=True,
                    )
                    if owns_session:
                        session.commit()
                    return execution
            preview = (
                session.query(WordPressChangePreview)
                .filter(
                    WordPressChangePreview.execution_id == execution.id,
                    WordPressChangePreview.status == 'approved',
                )
                .order_by(
                    WordPressChangePreview.approved_at.desc(),
                    WordPressChangePreview.created_at.desc(),
                )
                .first()
            )
            preview_snapshot = (
                preview.snapshot if preview is not None and isinstance(preview.snapshot, dict) else {}
            )
            affected_urls = (
                [str(value) for value in (preview_snapshot.get('affected_urls') or [])]
                if preview is not None
                else None
            )
            automation_decision = evaluate_wordpress_automation(
                session,
                campaign_id=execution.campaign_id,
                execution_type=execution.execution_type,
                risk_tier=int(recommendation.risk_tier or 1),
                affected_urls=affected_urls,
                exclude_execution_id=execution.id,
            )
            if not automation_decision.allowed:
                execution.status = 'pending'
                execution.last_error = automation_decision.reason_code
                execution.result_summary = json.dumps(
                    _governance_block(
                        campaign_id=execution.campaign_id,
                        execution_type=execution.execution_type,
                        reason_code=automation_decision.reason_code,
                        message=automation_decision.message,
                    ),
                    sort_keys=True,
                )
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
        if requires_wordpress_preview(execution) and not (execution.approved_by and execution.approved_at):
            execution.status = 'pending'
            execution.last_error = 'wordpress_preview_approval_required'
            execution.result_summary = json.dumps(
                _governance_block(
                    campaign_id=execution.campaign_id,
                    execution_type=execution.execution_type,
                    reason_code='wordpress_preview_approval_required',
                    message='Check and approve the exact website changes before running them.',
                ),
                sort_keys=True,
            )
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
        if is_managed_wordpress_execution(execution):
            _prepare_managed_measurement_if_possible(
                session,
                execution=execution,
                recommendation=recommendation,
            )
        try:
            result = _normalize_result(executor.run(payload), execution.execution_type)
            # Website delivery is external, while its mutation audit is local.
            # A savepoint keeps the session usable if audit persistence fails;
            # the plugin's stable mutation IDs make a later retry idempotent.
            with session.begin_nested():
                result = _deliver_mutations(session, execution=execution, result=result)
        except Exception:  # noqa: BLE001
            logger.exception(
                "recommendation execution failed",
                extra={
                    "execution_id": execution.id,
                    "campaign_id": execution.campaign_id,
                    "execution_type": execution.execution_type,
                    "attempt_count": int(execution.attempt_count or 0),
                },
            )
            result = _failed_result(
                execution.execution_type,
                'The action could not be completed safely. Review the connection, then try again.',
            )
            result['reason_code'] = 'execution_internal_error'
        if result['status'] == 'failed':
            if (
                is_managed_wordpress_execution(execution)
                and result.get('reason_code') == 'wordpress_public_verification_failed'
            ):
                paused_policy = pause_wordpress_automation_policy(
                    session,
                    campaign_id=execution.campaign_id,
                    reason_code='wordpress_public_verification_failed',
                    execution_id=execution.id,
                )
                if paused_policy is not None:
                    result['managed_automation_paused'] = True
                    result['automation_policy_version'] = int(paused_policy.version)
                    result['recovery_action'] = (
                        'Managed website updates were paused. Review the failed public checks '
                        'and roll back the saved change if needed before removing the pause.'
                    )
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
        if is_managed_wordpress_execution(execution):
            result['post_change_measurement'] = _schedule_managed_follow_up_if_possible(
                session,
                execution=execution,
                result=result,
            )
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
        if execution.status not in {'completed', 'failed'}:
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
        _mark_recommendation_rolled_back(
            session,
            recommendation=recommendation,
            execution=execution,
            requested_by=requested_by,
        )
        outbox_event_write(session, tenant_id=recommendation.tenant_id, event_type='execution.rolled_back', payload=_execution_event_payload(execution=execution, result_summary={'requested_by': requested_by, 'rolled_back_mutations': rollback_results}))
        if owns_session:
            session.commit()
            session.refresh(execution)
        return execution
    finally:
        if owns_session:
            session.close()


def approve_execution(execution_id: str, *, approved_by: str, preview_hash: str | None = None, db: Session | None = None) -> RecommendationExecution | None:
    owns_session = db is None
    session = db or SessionLocal()
    try:
        execution = session.get(RecommendationExecution, execution_id)
        if execution is None:
            return None
        if requires_wordpress_preview(execution):
            approve_change_preview(
                session,
                execution=execution,
                preview_hash=preview_hash,
                approved_by=approved_by,
            )
        execution.approved_by = approved_by
        execution.approved_at = datetime.now(UTC)
        if execution.status == 'pending' or (
            execution.status == 'failed' and requires_wordpress_preview(execution)
        ):
            execution.status = 'scheduled'
            execution.last_error = None
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
        if execution.status not in {'failed', 'running'}:
            return execution
        interrupted = execution.status == 'running' and execution.executed_at is None
        if execution.status == 'running' and not interrupted:
            return execution
        if int(execution.attempt_count or 0) >= RETRY_LIMIT:
            if interrupted:
                execution.status = 'failed'
                execution.last_error = 'retry limit exceeded'
                execution.result_summary = json.dumps(
                    _failed_result(
                        execution.execution_type,
                        'This interrupted action reached its retry limit. Review it before trying again.',
                    ),
                    sort_keys=True,
                )
                execution.executed_at = datetime.now(UTC)
                session.flush()
            return execution
        execution.status = 'scheduled'
        execution.last_error = None
        session.flush()
        recommendation = session.get(StrategyRecommendation, execution.recommendation_id)
        if recommendation is not None:
            outbox_event_write(
                session,
                tenant_id=recommendation.tenant_id,
                event_type='execution.recovered' if interrupted else 'execution.scheduled',
                payload=_execution_event_payload(execution=execution, result_summary=None),
            )
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


def _mark_recommendation_rolled_back(
    session: Session,
    *,
    recommendation: StrategyRecommendation,
    execution: RecommendationExecution,
    requested_by: str,
) -> None:
    """Record a rollback without bypassing terminal-output immutability.

    Production Postgres deliberately blocks direct updates to terminal strategy
    records. Its governed override function records the actor and reason in the
    audit log before changing ``EXECUTED`` to ``ROLLED_BACK``. Test databases do
    not install that Postgres function, so they use the equivalent ORM update.
    """
    dialect_name = session.get_bind().dialect.name
    if dialect_name == 'postgresql':
        session.execute(
            text(
                """
                SELECT governed_override_strategy_recommendation(
                    :recommendation_id,
                    :actor_user_id,
                    :reason,
                    CAST(:new_status AS strategy_recommendation_status),
                    NULL
                )
                """
            ),
            {
                'recommendation_id': recommendation.id,
                'actor_user_id': requested_by,
                'reason': (
                    f'Execution {execution.id} rollback completed using its '
                    'persisted mutation snapshot.'
                ),
                'new_status': StrategyRecommendationStatus.ROLLED_BACK.value,
            },
        )
        return
    recommendation.status = StrategyRecommendationStatus.ROLLED_BACK


def _record_outcome_if_possible(session: Session, execution: RecommendationExecution, result: dict[str, Any]) -> None:
    if execution.status != 'completed':
        return
    try:
        # Outcome learning is derived bookkeeping. It must never turn a
        # successfully delivered and audited website change into an API 500.
        # Isolate it in a savepoint so the primary action can still commit.
        with session.begin_nested():
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
            record_execution_outcome(
                session,
                execution=execution,
                metric_before=metric_before,
                metric_after=metric_after,
                commit=False,
            )
    except Exception:  # noqa: BLE001
        logger.exception(
            'execution outcome recording failed; primary action remains completed',
            extra={
                'execution_id': execution.id,
                'campaign_id': execution.campaign_id,
                'execution_type': execution.execution_type,
            },
        )


def _prepare_managed_measurement_if_possible(
    session: Session,
    *,
    execution: RecommendationExecution,
    recommendation: StrategyRecommendation,
) -> dict[str, Any]:
    try:
        with session.begin_nested():
            return prepare_managed_wordpress_measurement(
                session,
                execution=execution,
                recommendation=recommendation,
                prepared_at=datetime.now(UTC),
            )
    except Exception:  # noqa: BLE001
        logger.exception(
            'managed WordPress baseline capture failed; primary action can continue',
            extra={
                'execution_id': execution.id,
                'campaign_id': execution.campaign_id,
                'execution_type': execution.execution_type,
            },
        )
        return {
            'required': True,
            'status': 'unavailable',
            'reason_code': 'wordpress_measurement_baseline_failed',
            'message': 'The website action can continue, but its starting measurement is unavailable.',
        }


def _schedule_managed_follow_up_if_possible(
    session: Session,
    *,
    execution: RecommendationExecution,
    result: dict[str, Any],
) -> dict[str, Any]:
    try:
        with session.begin_nested():
            return schedule_managed_wordpress_follow_up(
                session,
                execution=execution,
                result_summary=result,
                completed_at=execution.executed_at,
            )
    except Exception:  # noqa: BLE001
        logger.exception(
            'managed WordPress follow-up scheduling failed; primary action remains completed',
            extra={
                'execution_id': execution.id,
                'campaign_id': execution.campaign_id,
                'execution_type': execution.execution_type,
            },
        )
        return {
            'required': is_managed_wordpress_execution(execution),
            'status': 'unavailable',
            'reason_code': 'wordpress_measurement_schedule_failed',
            'message': 'The website change completed, but its automatic result check could not be scheduled.',
        }


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
    for optional_key in ('metric_name', 'metric_before', 'metric_after', 'delta', 'delivery_mode', 'provider_name', 'mutation_results', 'public_verification', 'rollback_available', 'recovery_action', 'rollback_delivery_mode', 'rolled_back_mutations'):
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


def _build_execution_payload(
    *,
    recommendation: StrategyRecommendation,
    campaign: Campaign,
    metric_name: str,
    metric_before: float,
    idempotency_key: str,
    requires_manual_approval: bool,
    managed_wordpress_automation: bool = False,
    automation_policy_version: int | None = None,
) -> dict[str, Any]:
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
        'managed_wordpress_automation': managed_wordpress_automation,
        'automation_policy_version': automation_policy_version,
        'recommendation_context': evidence,
        'rollback_plan': rollback_plan,
    }
    if isinstance(evidence, dict):
        for key in (
            'source_url',
            'target_url',
            'anchor_text',
            'schema_type',
            'content_title',
            'content_slug',
            'content_target_url',
            'meta_title',
            'meta_description',
            'content_generation_mode',
            'governed_ai_run_id',
            'content_blocks',
            'content_draft_id',
            'content_draft_revision',
            'content_draft_hash',
            'content_brief_id',
        ):
            if key in evidence and evidence[key] is not None:
                payload[key] = evidence[key]
    return payload


def _deliver_mutations(session: Session, *, execution: RecommendationExecution, result: dict[str, Any]) -> dict[str, Any]:
    mutations = result.get('mutations', [])
    if not mutations:
        return result
    campaign = session.get(Campaign, execution.campaign_id)
    try:
        require_commercial_feature(
            session,
            organization_id=campaign.organization_id if campaign is not None else None,
            feature_code=FEATURE_WORDPRESS_EXECUTION,
        )
    except CostEconomicsError as exc:
        failed = _failed_result(execution.execution_type, str(exc))
        failed['reason_code'] = exc.reason_code
        failed['mutations'] = mutations
        return failed
    try:
        mutations = bind_approved_preview(session, execution=execution, mutations=mutations)
    except WordPressChangePreviewError as exc:
        failed = _failed_result(execution.execution_type, str(exc))
        failed['reason_code'] = exc.reason_code
        failed['mutations'] = mutations
        return failed
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
    verification = delivery.get('public_verification')
    if isinstance(verification, dict):
        result['public_verification'] = verification
        result['rollback_available'] = bool(verification.get('rollback_available'))
        if not bool(verification.get('passed')):
            result['status'] = 'failed'
            result['reason_code'] = 'wordpress_public_verification_failed'
            result['recovery_action'] = (
                'Review the failed public checks. Roll back the saved website change if it is not visible as approved.'
            )
            result['notes'] = (
                'WordPress saved the change, but the public website did not match every approved value. '
                'A rollback snapshot is available.'
            )
            return result
    result['notes'] = f"{result.get('notes', '').strip()} Mutation delivery and public verification completed.".strip()
    return result


def _persist_mutation_audit_rows(session: Session, *, execution: RecommendationExecution, delivery: dict[str, Any], mutations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    now = datetime.now(UTC)
    results = delivery.get('results', []) if isinstance(delivery.get('results'), list) else []
    by_id = {str(item.get('mutation_id') or ''): item for item in results if isinstance(item, dict)}
    verification = delivery.get('public_verification')
    verification_results = (
        verification.get('results', []) if isinstance(verification, dict) else []
    )
    verification_by_id = {
        str(item.get('mutation_id') or ''): item
        for item in verification_results
        if isinstance(item, dict)
    }
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
        row_verification = verification_by_id.get(str(row.external_mutation_id or ''), {})
        rows.append({
            'mutation_id': row.external_mutation_id,
            'mutation_type': row.mutation_type,
            'target_url': row.target_url,
            'status': row.status,
            'public_verification': row_verification,
            'rollback_available': bool(result.get('rollback_payload')),
        })
    session.flush()
    return rows

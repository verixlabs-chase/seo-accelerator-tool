from __future__ import annotations

import json
from datetime import UTC, datetime
from hashlib import sha256
from time import perf_counter
from typing import Any

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.enums import StrategyRecommendationStatus
from app.intelligence.digital_twin.strategy_optimizer import optimize_strategy
from app.intelligence.digital_twin.twin_state_model import DigitalTwinState
from app.intelligence.feature_store import compute_features
from app.intelligence.legacy_adapters.diagnostic_adapter import collect_legacy_diagnostics
from app.intelligence.legacy_adapters.executive_summary_adapter import build_legacy_packaging
from app.intelligence.legacy_adapters.scenario_registry_adapter import diagnostics_to_patterns, diagnostics_to_policy_inputs
from app.intelligence.campaign_workers.campaign_worker_pool import CampaignWorkerPool
from app.intelligence.intelligence_metrics_aggregator import compute_campaign_metrics
from app.intelligence.pattern_engine import detect_patterns, discover_cohort_patterns
from app.intelligence.policy_engine import derive_policy, generate_recommendations, score_policy
from app.intelligence.policy_update_engine import update_policy_priority_weights, update_policy_weights
from app.intelligence.recommendation_execution_engine import execute_recommendation, schedule_execution
from app.intelligence.strategy_transfer_engine import transfer_strategies
from app.intelligence.signal_assembler import assemble_signals
from app.intelligence.temporal_ingestion import write_temporal_signals
from app.models.campaign import Campaign
from app.models.organization import Organization
from app.models.intelligence import StrategyRecommendation
from app.models.recommendation_execution import RecommendationExecution
from app.models.recommendation_outcome import RecommendationOutcome
from app.utils.enum_guard import ensure_enum


PIPELINE_VERSION = 'orchestrator-v1'
PIPELINE_STAGES: tuple[str, ...] = (
    'assemble_signals',
    'write_temporal_signals',
    'compute_features',
    'detect_patterns',
    'discover_cohort_patterns',
    'generate_recommendations',
    'digital_twin_selection',
    'execution_scheduling',
    'execution_runtime',
    'policy_learning',
    'metrics_aggregation',
)

# In-memory stage timings keyed by campaign id.
pipeline_timings: dict[str, dict[str, float]] = {}


def run_campaign_cycle(campaign_id: str, db: Session | None = None) -> dict[str, Any]:
    owns_session = db is None
    session = db or SessionLocal()
    try:
        campaign = session.get(Campaign, campaign_id)
        if campaign is None:
            raise ValueError(f'Campaign not found: {campaign_id}')

        cycle_started_at = datetime.now(UTC)
        campaign_started_perf = perf_counter()
        stage_timings: dict[str, float] = {}

        stage_started = perf_counter()
        signals = assemble_signals(campaign_id, db=session)
        stage_timings['assemble_signals'] = round((perf_counter() - stage_started) * 1000.0, 3)

        stage_started = perf_counter()
        temporal_write_result = write_temporal_signals(
            campaign_id,
            signals,
            db=session,
            observed_at=cycle_started_at,
            source='orchestrator_signal_assembler_v1',
        )
        stage_timings['write_temporal_signals'] = round((perf_counter() - stage_started) * 1000.0, 3)

        stage_started = perf_counter()
        features = compute_features(campaign_id, db=session, persist=True)
        stage_timings['compute_features'] = round((perf_counter() - stage_started) * 1000.0, 3)

        stage_started = perf_counter()
        direct_patterns = [
            {
                'pattern_key': item.pattern_key,
                'confidence': float(item.confidence),
                'evidence': list(item.evidence),
            }
            for item in detect_patterns(features)
        ]
        stage_timings['detect_patterns'] = round((perf_counter() - stage_started) * 1000.0, 3)

        stage_started = perf_counter()
        cohort_patterns = discover_cohort_patterns(session, campaign_id=campaign_id, features=features)
        stage_timings['discover_cohort_patterns'] = round((perf_counter() - stage_started) * 1000.0, 3)

        stage_started = perf_counter()
        runtime_tier = _campaign_runtime_tier(session, campaign)
        legacy_diagnostics = collect_legacy_diagnostics(
            campaign_id=campaign.id,
            raw_signals=signals,
            db=session,
            tier=runtime_tier,
        )
        legacy_patterns = diagnostics_to_patterns(legacy_diagnostics)
        legacy_policies = diagnostics_to_policy_inputs(legacy_diagnostics)
        recommendations = _generate_and_persist_recommendations(
            session,
            campaign=campaign,
            features=features,
            direct_patterns=direct_patterns,
            cohort_patterns=cohort_patterns,
            legacy_patterns=legacy_patterns,
            legacy_policies=legacy_policies,
            cycle_started_at=cycle_started_at,
        )
        legacy_packaging = build_legacy_packaging(
            campaign_id=campaign.id,
            tier=runtime_tier,
            window=_current_window(cycle_started_at),
            recommendations=recommendations,
            detected_scenarios=[item.scenario_id for item in legacy_diagnostics],
            generated_at=cycle_started_at.isoformat(),
        )
        stage_timings['generate_recommendations'] = round((perf_counter() - stage_started) * 1000.0, 3)

        stage_started = perf_counter()
        selected_recommendations, simulation_result = _select_recommendations_via_digital_twin(
            session,
            campaign_id=campaign.id,
            recommendations=recommendations,
        )
        stage_timings['digital_twin_selection'] = round((perf_counter() - stage_started) * 1000.0, 3)

        stage_started = perf_counter()
        scheduled_executions = _schedule_recommendation_executions(session, selected_recommendations)
        stage_timings['execution_scheduling'] = round((perf_counter() - stage_started) * 1000.0, 3)

        stage_started = perf_counter()
        completed_executions = _execute_scheduled_executions(session, scheduled_executions)
        stage_timings['execution_runtime'] = round((perf_counter() - stage_started) * 1000.0, 3)

        outcomes_recorded = _count_outcomes_since(session, campaign_id, cycle_started_at)

        stage_started = perf_counter()
        recommendation_weights = update_policy_weights(session)
        policy_priority_weights = update_policy_priority_weights(session)
        stage_timings['policy_learning'] = round((perf_counter() - stage_started) * 1000.0, 3)

        stage_started = perf_counter()
        metrics_snapshot = compute_campaign_metrics(campaign_id, db=session, metric_date=cycle_started_at.date())
        stage_timings['metrics_aggregation'] = round((perf_counter() - stage_started) * 1000.0, 3)

        total_runtime_ms = round((perf_counter() - campaign_started_perf) * 1000.0, 3)
        pipeline_timings[campaign_id] = dict(stage_timings)

        if owns_session:
            session.commit()

        return {
            'campaign_id': campaign_id,
            'pipeline_version': PIPELINE_VERSION,
            'cycle_started_at': cycle_started_at.isoformat(),
            'signals_processed': len(signals),
            'temporal_signals_inserted': int(temporal_write_result.get('inserted', 0)),
            'temporal_signals_skipped': int(temporal_write_result.get('skipped', 0)),
            'features_computed': len(features),
            'patterns_detected': len(direct_patterns),
            'cohort_patterns_detected': len(cohort_patterns),
            'recommendations_generated': len(recommendations),
            'recommendation_ids': sorted([row.id for row in recommendations]),
            'recommendations_selected_for_execution': len(selected_recommendations),
            'selected_recommendation_ids': sorted([row.id for row in selected_recommendations]),
            'digital_twin_selection': simulation_result,
            'legacy_packaging': legacy_packaging,
            'executions_scheduled': len(scheduled_executions),
            'executions_completed': len(completed_executions),
            'execution_ids': sorted([row.id for row in completed_executions]),
            'outcomes_recorded': outcomes_recorded,
            'policy_learning': {
                'recommendation_weight_count': len(recommendation_weights),
                'policy_priority_weight_count': len(policy_priority_weights),
            },
            'metrics_snapshot_id': metrics_snapshot.id,
            'metrics_snapshot_date': metrics_snapshot.metric_date.isoformat(),
            'pipeline_timings': {
                'campaign_id': campaign_id,
                'timings': stage_timings,
                'total_runtime_ms': total_runtime_ms,
            },
        }
    finally:
        if owns_session:
            session.close()


def run_system_cycle(db: Session | None = None) -> dict[str, Any]:
    owns_session = db is None
    session = db or SessionLocal()
    try:
        active_campaigns = (
            session.query(Campaign)
            .filter(Campaign.setup_state.in_(['Active', 'active']))
            .order_by(Campaign.created_at.asc(), Campaign.id.asc())
            .all()
        )

        campaign_ids = [campaign.id for campaign in active_campaigns]
        summaries: list[dict[str, Any]] = []
        assignments: dict[str, int] = {}
        worker_count = 1

        if campaign_ids:
            if owns_session:
                worker_count = min(8, max(1, len(campaign_ids)))
                pool = CampaignWorkerPool(
                    worker_count=worker_count,
                    processor=lambda cid: run_campaign_cycle(cid, db=None),
                )
                assignments, result_map = pool.process_campaigns(campaign_ids)
                summaries = [result_map[campaign_id] for campaign_id in campaign_ids if campaign_id in result_map]
            else:
                # Shared SQLAlchemy sessions are not thread-safe; keep deterministic fallback for injected sessions.
                summaries = [run_campaign_cycle(campaign_id, db=session) for campaign_id in campaign_ids]
                assignments = {campaign_id: 0 for campaign_id in campaign_ids}

        stage_totals: dict[str, float] = {stage: 0.0 for stage in PIPELINE_STAGES}
        stage_counts: dict[str, int] = {stage: 0 for stage in PIPELINE_STAGES}
        campaign_runtimes_ms: list[float] = []
        per_campaign_total_runtime_ms: dict[str, float] = {}

        for item in summaries:
            campaign_id = str(item.get('campaign_id', ''))
            timings_payload = item.get('pipeline_timings', {})
            if not isinstance(timings_payload, dict):
                continue

            stage_values = timings_payload.get('timings', {})
            if isinstance(stage_values, dict):
                for stage in PIPELINE_STAGES:
                    value = stage_values.get(stage)
                    if isinstance(value, (int, float)):
                        stage_totals[stage] += float(value)
                        stage_counts[stage] += 1

            total_value = timings_payload.get('total_runtime_ms')
            if isinstance(total_value, (int, float)):
                runtime = float(total_value)
                campaign_runtimes_ms.append(runtime)
                if campaign_id:
                    per_campaign_total_runtime_ms[campaign_id] = runtime

        average_stage_runtime_ms = {
            stage: round(stage_totals[stage] / stage_counts[stage], 3)
            for stage in PIPELINE_STAGES
            if stage_counts[stage] > 0
        }
        slowest_stage = (
            max(average_stage_runtime_ms, key=lambda name: average_stage_runtime_ms[name])
            if average_stage_runtime_ms
            else None
        )
        avg_runtime_per_campaign_ms = round(sum(campaign_runtimes_ms) / len(campaign_runtimes_ms), 3) if campaign_runtimes_ms else 0.0

        print('STAGE PROFILE SUMMARY')
        for stage in PIPELINE_STAGES:
            value = average_stage_runtime_ms.get(stage)
            if value is None:
                continue
            suffix = '  <-- slowest stage' if slowest_stage == stage else ''
            print(f'{stage}: {value:.1f}ms avg{suffix}')
        print(f'avg_runtime_per_campaign: {avg_runtime_per_campaign_ms / 1000.0:.3f}s')

        if owns_session:
            session.commit()

        return {
            'pipeline_version': PIPELINE_VERSION,
            'campaigns_processed': len(summaries),
            'campaign_ids': sorted([item['campaign_id'] for item in summaries]),
            'summaries': summaries,
            'worker_fabric': {
                'enabled': bool(campaign_ids),
                'worker_count': worker_count,
                'assignments': assignments,
            },
            'stage_profile_summary': {
                'average_stage_runtime_ms': average_stage_runtime_ms,
                'slowest_stage': slowest_stage,
                'avg_runtime_per_campaign_ms': avg_runtime_per_campaign_ms,
                'total_runtime_per_campaign_ms': per_campaign_total_runtime_ms,
            },
        }
    finally:
        if owns_session:
            session.close()


def _generate_and_persist_recommendations(
    db: Session,
    *,
    campaign: Campaign,
    features: dict[str, float],
    direct_patterns: list[dict[str, Any]],
    cohort_patterns: list[dict[str, Any]],
    cycle_started_at: datetime,
    legacy_patterns: list[dict[str, Any]] | None = None,
    legacy_policies: list[dict[str, Any]] | None = None,
) -> list[StrategyRecommendation]:
    all_patterns = sorted(
        direct_patterns + cohort_patterns + list(legacy_patterns or []),
        key=lambda item: (str(item.get('pattern_key', '')), str(item.get('cohort', ''))),
    )

    policies = [score_policy(policy, features, db=db) for policy in _merge_policy_inputs(derive_policy(all_patterns), legacy_policies or [])]
    policy_recommendations = [
        recommendation
        for policy in policies
        for recommendation in generate_recommendations(policy)
    ]

    transfer_payload = transfer_strategies(campaign.id, db=db)
    transfer_strategies_list = transfer_payload.get('strategies', [])
    if isinstance(transfer_strategies_list, list):
        for strategy in transfer_strategies_list:
            if not isinstance(strategy, dict):
                continue
            strategy_id = str(strategy.get('strategy_id', '') or '')
            if not strategy_id:
                continue
            confidence = float(strategy.get('confidence', 0.0) or 0.0)
            forecast = strategy.get('forecast') if isinstance(strategy.get('forecast'), dict) else {}
            forecast_confidence = float(forecast.get('confidence_score', 0.0) or 0.0)
            forecast_risk = float(forecast.get('risk_score', 0.0) or 0.0)
            transfer_priority = confidence * max(forecast_confidence, 0.1) * max(0.1, 1.0 - forecast_risk)
            risk_tier = 1 if forecast_risk < 0.34 else 2 if forecast_risk < 0.67 else 3
            policy_recommendations.append(
                {
                    'recommendation_type': f'transfer::{strategy_id}',
                    'action': strategy_id,
                    'risk_tier': risk_tier,
                    'priority_weight': max(0.1, min(transfer_priority, 1.0)),
                    'policy_id': 'transfer_engine',
                }
            )

    persisted: list[StrategyRecommendation] = []
    for recommendation in policy_recommendations:
        recommendation_type = str(recommendation.get('recommendation_type', 'policy::unknown::action'))
        action = str(recommendation.get('action', 'unknown_action'))
        risk_tier = int(recommendation.get('risk_tier', 2) or 2)
        priority_weight = float(recommendation.get('priority_weight', 0.5) or 0.5)
        policy_id = str(recommendation.get('policy_id', 'unknown_policy'))

        idempotency_key = f'{campaign.id}:{cycle_started_at.date().isoformat()}:{policy_id}:{action}'

        existing = (
            db.query(StrategyRecommendation)
            .filter(
                StrategyRecommendation.tenant_id == campaign.tenant_id,
                StrategyRecommendation.campaign_id == campaign.id,
                StrategyRecommendation.idempotency_key == idempotency_key,
            )
            .first()
        )
        if existing is not None:
            persisted.append(existing)
            continue

        evidence_json = json.dumps(
            {
                'patterns': all_patterns,
                'features': {key: round(float(value), 6) for key, value in sorted(features.items())},
                'policy_id': policy_id,
                'legacy_source_scenario_id': recommendation.get('legacy_source_scenario_id'),
                'operator_explanation': recommendation.get('operator_explanation'),
            },
            sort_keys=True,
        )

        row = StrategyRecommendation(
            tenant_id=campaign.tenant_id,
            campaign_id=campaign.id,
            recommendation_type=recommendation_type,
            rationale=str(recommendation.get('rationale') or f'Deterministic recommendation from {policy_id}:{action}'),
            confidence=round(priority_weight, 6),
            confidence_score=round(priority_weight, 6),
            evidence_json=evidence_json,
            risk_tier=risk_tier,
            rollback_plan_json=json.dumps({'steps': ['revert_automation_action']}, sort_keys=True),
            status=ensure_enum(StrategyRecommendationStatus.APPROVED, StrategyRecommendationStatus),
            idempotency_key=idempotency_key,
            input_hash=_hash_payload(features),
            output_hash=_hash_payload(recommendation),
            build_hash=_hash_payload({'policy_id': policy_id, 'action': action, 'idempotency_key': idempotency_key}),
        )
        db.add(row)
        db.flush()
        persisted.append(row)

    if not persisted:
        fallback_key = f'{campaign.id}:{cycle_started_at.date().isoformat()}:fallback:stabilize_foundations'
        existing_fallback = (
            db.query(StrategyRecommendation)
            .filter(
                StrategyRecommendation.tenant_id == campaign.tenant_id,
                StrategyRecommendation.campaign_id == campaign.id,
                StrategyRecommendation.idempotency_key == fallback_key,
            )
            .first()
        )
        if existing_fallback is not None:
            persisted.append(existing_fallback)
        else:
            fallback = StrategyRecommendation(
                tenant_id=campaign.tenant_id,
                campaign_id=campaign.id,
                recommendation_type='policy::fallback::stabilize_foundations',
                rationale='Deterministic fallback recommendation due to no matched patterns',
                confidence=0.6,
                confidence_score=0.6,
                evidence_json=json.dumps({'patterns': all_patterns, 'features': features}, sort_keys=True),
                risk_tier=1,
                rollback_plan_json=json.dumps({'steps': ['revert_automation_action']}, sort_keys=True),
                status=ensure_enum(StrategyRecommendationStatus.APPROVED, StrategyRecommendationStatus),
                idempotency_key=fallback_key,
                input_hash=_hash_payload(features),
                output_hash=_hash_payload({'recommendation_type': 'policy::fallback::stabilize_foundations'}),
                build_hash=_hash_payload({'fallback_key': fallback_key}),
            )
            db.add(fallback)
            db.flush()
            persisted.append(fallback)

    return sorted(persisted, key=lambda row: row.id)


def _schedule_recommendation_executions(db: Session, recommendations: list[StrategyRecommendation]) -> list[RecommendationExecution]:
    executions: list[RecommendationExecution] = []
    for recommendation in sorted(recommendations, key=lambda row: row.id):
        execution = schedule_execution(recommendation.id, db=db)
        if execution is not None:
            executions.append(execution)
    return executions


def _execute_scheduled_executions(db: Session, executions: list[RecommendationExecution]) -> list[RecommendationExecution]:
    completed: list[RecommendationExecution] = []
    for execution in sorted(executions, key=lambda row: row.id):
        result = execute_recommendation(execution.id, db=db, dry_run=False)
        if isinstance(result, RecommendationExecution):
            completed.append(result)
    return completed


def _select_recommendations_via_digital_twin(
    db: Session,
    *,
    campaign_id: str,
    recommendations: list[StrategyRecommendation],
) -> tuple[list[StrategyRecommendation], dict[str, Any]]:
    ordered = sorted(recommendations, key=lambda row: row.id)
    if not ordered:
        return [], {'status': 'no_recommendations', 'selected_recommendation_ids': []}

    candidate_strategies: list[dict[str, Any]] = []
    by_strategy_id: dict[str, StrategyRecommendation] = {}
    for recommendation in ordered:
        strategy_id = f'recommendation:{recommendation.id}'
        candidate_strategies.append(
            {
                'strategy_id': strategy_id,
                'recommendation_id': recommendation.id,
                'strategy_actions': _recommendation_to_strategy_actions(recommendation.recommendation_type),
            }
        )
        by_strategy_id[strategy_id] = recommendation

    try:
        twin_state = DigitalTwinState.from_campaign_data(db, campaign_id)
        winning = optimize_strategy(twin_state, candidate_strategies, db=db)
    except Exception as exc:  # pragma: no cover
        return ordered, {
            'status': 'failed_open',
            'error': str(exc),
            'selected_recommendation_ids': [row.id for row in ordered],
        }

    if winning is None:
        return ordered, {'status': 'no_candidates', 'selected_recommendation_ids': [row.id for row in ordered]}

    strategy_id = str(winning.get('strategy_id', '') or '')
    selected = by_strategy_id.get(strategy_id)
    if selected is None:
        return ordered, {'status': 'winner_unmapped', 'selected_recommendation_ids': [row.id for row in ordered]}

    simulation = winning.get('simulation') if isinstance(winning.get('simulation'), dict) else {}
    return [selected], {
        'status': 'optimized',
        'winning_strategy_id': strategy_id,
        'selected_recommendation_ids': [selected.id],
        'expected_value': float(winning.get('expected_value', 0.0) or 0.0),
        'simulation_id': simulation.get('simulation_id'),
    }


def _recommendation_to_strategy_actions(recommendation_type: str) -> list[dict[str, int | str]]:
    normalized = recommendation_type.lower()
    if 'internal' in normalized or 'link' in normalized:
        return [{'type': 'internal_link', 'count': 1}]
    if 'title' in normalized or 'schema' in normalized or 'fix' in normalized or 'gbp' in normalized:
        return [{'type': 'fix_technical_issues', 'count': 1}]
    return [{'type': 'publish_content', 'pages': 1}]


def _count_outcomes_since(db: Session, campaign_id: str, started_at: datetime) -> int:
    return int(
        db.query(RecommendationOutcome)
        .filter(
            RecommendationOutcome.campaign_id == campaign_id,
            RecommendationOutcome.measured_at >= started_at,
        )
        .count()
    )


def _hash_payload(payload: Any) -> str:
    packed = json.dumps(payload, sort_keys=True, default=str)
    return sha256(packed.encode('utf-8')).hexdigest()



def _merge_policy_inputs(base_policies: list[dict[str, Any]], legacy_policies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for item in list(base_policies) + list(legacy_policies):
        policy_id = str(item.get('policy_id', '') or '')
        if not policy_id:
            continue
        existing = merged.get(policy_id)
        if existing is None:
            merged[policy_id] = {
                **dict(item),
                'recommended_actions': list(item.get('recommended_actions', [])),
                'source_patterns': list(item.get('source_patterns', [])),
            }
            continue
        existing['priority_weight'] = max(float(existing.get('priority_weight', 0.0) or 0.0), float(item.get('priority_weight', 0.0) or 0.0))
        existing['pattern_confidence'] = max(float(existing.get('pattern_confidence', 0.0) or 0.0), float(item.get('pattern_confidence', 0.0) or 0.0))
        existing['recommended_actions'] = sorted(set(existing.get('recommended_actions', []) + list(item.get('recommended_actions', []))))
        existing['source_patterns'] = sorted(set(existing.get('source_patterns', []) + list(item.get('source_patterns', []))))
        for key in ('legacy_source_scenario_id', 'rationale', 'operator_explanation', 'risk_tier'):
            if key in item and item.get(key) is not None:
                existing[key] = item.get(key)
    return [merged[key] for key in sorted(merged)]


def _campaign_runtime_tier(db: Session, campaign: Campaign) -> str:
    if campaign.organization_id:
        org_row = db.query(Organization).filter(Organization.id == campaign.organization_id).first()
        if org_row is not None:
            plan = str(org_row.plan_type or 'standard').strip().lower()
            if plan == 'enterprise':
                return 'enterprise'
            if plan in {'pro', 'internal_anchor'}:
                return 'pro'
            return plan
    return 'standard'


def _current_window(now: datetime):
    from app.services.strategy_engine.schemas import StrategyWindow

    return StrategyWindow(date_from=now.replace(day=1), date_to=now)

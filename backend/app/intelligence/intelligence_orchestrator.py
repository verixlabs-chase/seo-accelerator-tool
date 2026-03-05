from __future__ import annotations

import json
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.enums import StrategyRecommendationStatus
from app.intelligence.feature_store import compute_features
from app.intelligence.intelligence_metrics_aggregator import compute_campaign_metrics
from app.intelligence.pattern_engine import detect_patterns, discover_cohort_patterns
from app.intelligence.policy_engine import derive_policy, generate_recommendations, score_policy
from app.intelligence.policy_update_engine import update_policy_priority_weights, update_policy_weights
from app.intelligence.recommendation_execution_engine import execute_recommendation, schedule_execution
from app.intelligence.signal_assembler import assemble_signals
from app.intelligence.temporal_ingestion import write_temporal_signals
from app.models.campaign import Campaign
from app.models.intelligence import StrategyRecommendation
from app.models.recommendation_execution import RecommendationExecution
from app.models.recommendation_outcome import RecommendationOutcome
from app.utils.enum_guard import ensure_enum


PIPELINE_VERSION = 'orchestrator-v1'


def run_campaign_cycle(campaign_id: str, db: Session | None = None) -> dict[str, Any]:
    owns_session = db is None
    session = db or SessionLocal()
    try:
        campaign = session.get(Campaign, campaign_id)
        if campaign is None:
            raise ValueError(f'Campaign not found: {campaign_id}')

        cycle_started_at = datetime.now(UTC)

        signals = assemble_signals(campaign_id, db=session)
        temporal_write_result = write_temporal_signals(
            campaign_id,
            signals,
            db=session,
            observed_at=cycle_started_at,
            source='orchestrator_signal_assembler_v1',
        )

        features = compute_features(campaign_id, db=session, persist=True)

        direct_patterns = [
            {
                'pattern_key': item.pattern_key,
                'confidence': float(item.confidence),
                'evidence': list(item.evidence),
            }
            for item in detect_patterns(features)
        ]
        cohort_patterns = discover_cohort_patterns(session, campaign_id=campaign_id, features=features)

        recommendations = _generate_and_persist_recommendations(
            session,
            campaign=campaign,
            features=features,
            direct_patterns=direct_patterns,
            cohort_patterns=cohort_patterns,
            cycle_started_at=cycle_started_at,
        )

        scheduled_executions = _schedule_recommendation_executions(session, recommendations)
        completed_executions = _execute_scheduled_executions(session, scheduled_executions)

        outcomes_recorded = _count_outcomes_since(session, campaign_id, cycle_started_at)

        recommendation_weights = update_policy_weights(session)
        policy_priority_weights = update_policy_priority_weights(session)

        metrics_snapshot = compute_campaign_metrics(campaign_id, db=session, metric_date=cycle_started_at.date())

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

        summaries: list[dict[str, Any]] = []
        for campaign in active_campaigns:
            summaries.append(run_campaign_cycle(campaign.id, db=session))

        if owns_session:
            session.commit()

        return {
            'pipeline_version': PIPELINE_VERSION,
            'campaigns_processed': len(summaries),
            'campaign_ids': sorted([item['campaign_id'] for item in summaries]),
            'summaries': summaries,
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
) -> list[StrategyRecommendation]:
    all_patterns = sorted(
        direct_patterns + cohort_patterns,
        key=lambda item: (str(item.get('pattern_key', '')), str(item.get('cohort', ''))),
    )

    policies = [score_policy(policy, features) for policy in derive_policy(all_patterns)]
    policy_recommendations = [
        recommendation
        for policy in policies
        for recommendation in generate_recommendations(policy)
    ]

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
            },
            sort_keys=True,
        )

        row = StrategyRecommendation(
            tenant_id=campaign.tenant_id,
            campaign_id=campaign.id,
            recommendation_type=recommendation_type,
            rationale=f'Deterministic recommendation from {policy_id}:{action}',
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

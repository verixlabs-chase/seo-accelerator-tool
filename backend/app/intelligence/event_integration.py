from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.intelligence.feature_aggregator import aggregate_features, build_cohort_profiles
from app.intelligence.feature_store import compute_features
from app.intelligence.policy_update_engine import update_policy_priority_weights, update_policy_weights
from app.intelligence.signal_assembler import assemble_signals
from app.intelligence.temporal_ingestion import write_temporal_signals

LEARNING_TRIGGER_EVENTS = {
    'crawl.completed',
    'report.generated',
    'automation.action_executed',
    'recommendation.outcome_recorded',
}


def process_learning_event(db: Session, *, tenant_id: str, event_type: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    if event_type not in LEARNING_TRIGGER_EVENTS:
        return None

    result: dict[str, Any] = {
        'event_type': event_type,
        'signals_written': {'inserted': 0, 'skipped': 0},
        'cohorts': 0,
    }

    campaign_id = str(payload.get('campaign_id', '') or '')
    if campaign_id:
        signals = assemble_signals(campaign_id, db=db)
        result['signals_written'] = write_temporal_signals(
            campaign_id,
            signals,
            db=db,
            source=f'event:{event_type}',
            tenant_id=tenant_id,
        )
        compute_features(campaign_id, db=db, persist=True)

    cohort_rows = aggregate_features(db)
    result['cohorts'] = len(cohort_rows)
    result['cohort_profiles'] = len(build_cohort_profiles(db))

    if event_type == 'recommendation.outcome_recorded':
        result['recommendation_weight_updates'] = update_policy_weights(db)
        result['policy_weight_updates'] = update_policy_priority_weights(db)

    return result

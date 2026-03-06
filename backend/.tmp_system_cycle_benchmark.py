import json
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from time import perf_counter
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.intelligence import intelligence_orchestrator as orchestrator
from app.models.campaign import Campaign
from app.models.digital_twin_simulation import DigitalTwinSimulation
from app.models.intelligence import StrategyRecommendation
from app.models.intelligence_metrics_snapshot import IntelligenceMetricsSnapshot
from app.models.organization import Organization
from app.models.recommendation_execution import RecommendationExecution
from app.models.tenant import Tenant
from tests.helpers.economic_setup import ensure_test_tier_profile

BENCHMARK_LEVELS: list[tuple[str, int]] = [('small', 50), ('medium', 200), ('large', 500)]


class StageTimer:
    def __init__(self) -> None:
        self.durations = defaultdict(float)
        self.calls = defaultdict(int)

    def add(self, stage: str, elapsed: float) -> None:
        self.durations[stage] += elapsed
        self.calls[stage] += 1

    def as_dict(self) -> dict[str, dict[str, float | int]]:
        return {
            stage: {'seconds': round(self.durations[stage], 6), 'calls': int(self.calls[stage])}
            for stage in sorted(self.durations)
        }


def timed(stage: str, timer: StageTimer, fn: Callable[..., Any]) -> Callable[..., Any]:
    def _wrapped(*args: Any, **kwargs: Any) -> Any:
        start = perf_counter()
        try:
            return fn(*args, **kwargs)
        finally:
            timer.add(stage, perf_counter() - start)

    return _wrapped


def seed_campaigns(db: Session, count: int, prefix: str) -> tuple[str, list[str]]:
    db.query(Campaign).filter(Campaign.setup_state.in_(['Active', 'active'])).update(
        {'setup_state': 'Draft'}, synchronize_session=False
    )
    db.query(IntelligenceMetricsSnapshot).delete(synchronize_session=False)
    db.flush()

    tier = ensure_test_tier_profile(db)
    tenant = Tenant(id=str(uuid.uuid4()), name=f'{prefix}-tenant', status='Active', created_at=datetime.now(UTC))
    db.add(tenant)
    db.flush()

    org = Organization(
        id=str(uuid.uuid4()),
        name=f'{prefix}-org',
        plan_type='standard',
        billing_mode='subscription',
        status='active',
        tier_profile_id=tier.id,
        tier_version=tier.version,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db.add(org)
    db.flush()

    ids: list[str] = []
    now = datetime.now(UTC)
    for i in range(count):
        campaign = Campaign(
            tenant_id=tenant.id,
            organization_id=org.id,
            name=f'{prefix}-campaign-{i:04d}',
            domain=f'{prefix}-{i:04d}.example.test',
            setup_state='Active',
            created_at=now,
        )
        db.add(campaign)
        db.flush()
        ids.append(campaign.id)

    db.commit()
    return tenant.id, ids


def run_level(db: Session, level: str, campaign_count: int) -> dict[str, Any]:
    prefix = f'bench-{level}-{uuid.uuid4().hex[:6]}'
    tenant_id, seeded_ids = seed_campaigns(db, campaign_count, prefix)
    seeded_set = set(seeded_ids)

    stage_timer = StageTimer()
    originals = {
        'assemble_signals': orchestrator.assemble_signals,
        'write_temporal_signals': orchestrator.write_temporal_signals,
        'compute_features': orchestrator.compute_features,
        'detect_patterns': orchestrator.detect_patterns,
        'discover_cohort_patterns': orchestrator.discover_cohort_patterns,
        '_generate_and_persist_recommendations': orchestrator._generate_and_persist_recommendations,
        '_schedule_recommendation_executions': orchestrator._schedule_recommendation_executions,
        'execute_recommendation': orchestrator.execute_recommendation,
        'update_policy_weights': orchestrator.update_policy_weights,
        'update_policy_priority_weights': orchestrator.update_policy_priority_weights,
        'compute_campaign_metrics': orchestrator.compute_campaign_metrics,
        'run_campaign_cycle': orchestrator.run_campaign_cycle,
    }

    orchestrator.assemble_signals = timed('signals_stage', stage_timer, orchestrator.assemble_signals)
    orchestrator.write_temporal_signals = timed('signals_stage', stage_timer, orchestrator.write_temporal_signals)
    orchestrator.compute_features = timed('feature_computation', stage_timer, orchestrator.compute_features)
    orchestrator.detect_patterns = timed('pattern_detection', stage_timer, orchestrator.detect_patterns)
    orchestrator.discover_cohort_patterns = timed('pattern_detection', stage_timer, orchestrator.discover_cohort_patterns)
    orchestrator._generate_and_persist_recommendations = timed(
        'recommendation_generation', stage_timer, orchestrator._generate_and_persist_recommendations
    )
    orchestrator._schedule_recommendation_executions = timed(
        'execution_scheduling', stage_timer, orchestrator._schedule_recommendation_executions
    )
    orchestrator.execute_recommendation = timed('digital_twin_simulations', stage_timer, orchestrator.execute_recommendation)
    orchestrator.update_policy_weights = timed('policy_updates', stage_timer, orchestrator.update_policy_weights)
    orchestrator.update_policy_priority_weights = timed('policy_updates', stage_timer, orchestrator.update_policy_priority_weights)
    orchestrator.compute_campaign_metrics = timed('metrics_aggregation', stage_timer, orchestrator.compute_campaign_metrics)

    progress = {'count': 0}

    def _progress_run_campaign_cycle(campaign_id: str, db: Session | None = None) -> dict[str, Any]:
        result = originals['run_campaign_cycle'](campaign_id, db=db)
        if campaign_id in seeded_set:
            progress['count'] += 1
            print('[{}/{}] campaign processed'.format(progress['count'], campaign_count))
        return result

    orchestrator.run_campaign_cycle = _progress_run_campaign_cycle

    start = perf_counter()
    try:
        summary = orchestrator.run_system_cycle(db=db)
    finally:
        orchestrator.assemble_signals = originals['assemble_signals']
        orchestrator.write_temporal_signals = originals['write_temporal_signals']
        orchestrator.compute_features = originals['compute_features']
        orchestrator.detect_patterns = originals['detect_patterns']
        orchestrator.discover_cohort_patterns = originals['discover_cohort_patterns']
        orchestrator._generate_and_persist_recommendations = originals['_generate_and_persist_recommendations']
        orchestrator._schedule_recommendation_executions = originals['_schedule_recommendation_executions']
        orchestrator.execute_recommendation = originals['execute_recommendation']
        orchestrator.update_policy_weights = originals['update_policy_weights']
        orchestrator.update_policy_priority_weights = originals['update_policy_priority_weights']
        orchestrator.compute_campaign_metrics = originals['compute_campaign_metrics']
        orchestrator.run_campaign_cycle = originals['run_campaign_cycle']

    db.commit()
    elapsed = perf_counter() - start

    level_summaries = [item for item in summary.get('summaries', []) if item.get('campaign_id') in seeded_set]
    campaign_ids = [item.get('campaign_id') for item in level_summaries]

    simulations_run = int(db.query(DigitalTwinSimulation).filter(DigitalTwinSimulation.campaign_id.in_(campaign_ids)).count()) if campaign_ids else 0
    recommendations_generated = int(db.query(StrategyRecommendation).filter(StrategyRecommendation.campaign_id.in_(campaign_ids)).count()) if campaign_ids else 0
    executions_scheduled = int(db.query(RecommendationExecution).filter(RecommendationExecution.campaign_id.in_(campaign_ids)).count()) if campaign_ids else 0

    report = {
        'level': level,
        'campaigns_seeded': campaign_count,
        'campaigns_processed': len(level_summaries),
        'total_runtime_seconds': round(elapsed, 3),
        'average_runtime_per_campaign': round(elapsed / max(1, len(level_summaries)), 6),
        'simulations_executed': simulations_run,
        'recommendations_generated': recommendations_generated,
        'executions_scheduled': executions_scheduled,
        'stage_timings': stage_timer.as_dict(),
        'tenant_id': tenant_id,
    }

    print(json.dumps(report, sort_keys=True))
    return report


def main() -> None:
    db = SessionLocal()
    try:
        reports: list[dict[str, Any]] = []
        for level, size in BENCHMARK_LEVELS:
            print(f'=== running {level} benchmark ({size} campaigns) ===')
            reports.append(run_level(db, level, size))

        print('=== final benchmark summary ===')
        print(json.dumps({'benchmark_levels': reports, 'generated_at': datetime.now(UTC).isoformat()}, sort_keys=True))
    finally:
        db.close()


if __name__ == '__main__':
    main()

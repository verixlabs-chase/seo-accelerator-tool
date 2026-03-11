from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from hashlib import sha256
from statistics import mean
from time import perf_counter
from types import SimpleNamespace

from app.enums import StrategyRecommendationStatus
from app.events.queue import queue_stats, reset_queue_state
from app.events.subscriber_registry import register_default_subscribers, reset_registry
from app.intelligence import intelligence_orchestrator as orchestrator
from app.intelligence.outcome_tracker import record_execution_outcome
from app.models.campaign import Campaign
from app.models.experiment import Experiment, ExperimentAssignment
from app.models.intelligence import StrategyRecommendation
from app.models.knowledge_graph import KnowledgeEdge
from app.models.recommendation_execution import RecommendationExecution
from app.utils.enum_guard import ensure_enum


def test_intelligence_full_cycle_benchmark(db_session, create_test_org, monkeypatch) -> None:
    reset_registry()
    register_default_subscribers(force_reset=True)
    reset_queue_state()

    org = create_test_org(name='Full Cycle Benchmark Org')
    campaigns = []
    for index in range(100):
        campaign = Campaign(
            tenant_id=org.id,
            organization_id=org.id,
            name=f'Full Cycle Benchmark {index}',
            domain=f'full-cycle-{index}.example',
            setup_state='Active',
        )
        db_session.add(campaign)
        campaigns.append(campaign)
    db_session.flush()

    experiment = Experiment(
        policy_id='child-a',
        hypothesis='Benchmark cohort for child-a',
        experiment_type='strategy_evolution',
        cohort_size=100,
        status='active',
        industry='unknown',
    )
    db_session.add(experiment)
    db_session.flush()
    assignments = []
    for index, campaign in enumerate(campaigns):
        cohort = 'treatment' if index % 2 else 'control'
        assigned_policy_id = 'child-a' if cohort == 'treatment' else 'baseline::child-a'
        assignments.append(
            ExperimentAssignment(
                experiment_id=experiment.experiment_id,
                campaign_id=campaign.id,
                cohort=cohort,
                bucket=80 if cohort == 'treatment' else 20,
                assigned_policy_id=assigned_policy_id,
            )
        )
    db_session.add_all(assignments)
    db_session.commit()

    _accelerate_non_learning_stages(monkeypatch)
    monkeypatch.setattr(orchestrator, '_generate_and_persist_recommendations', _benchmark_recommendations)

    initial_edge_count = db_session.query(KnowledgeEdge).count()
    initial_experiment_count = db_session.query(Experiment).count()

    started_at = perf_counter()
    with ThreadPoolExecutor(max_workers=16) as executor:
        futures = [executor.submit(orchestrator.run_campaign_cycle, campaign.id, None) for campaign in campaigns]
        results = [future.result(timeout=120) for future in futures]
    elapsed = max(perf_counter() - started_at, 1e-6)

    db_session.expire_all()
    final_edge_count = db_session.query(KnowledgeEdge).count()
    final_experiment_count = db_session.query(Experiment).count()

    graph_edge_delta = max(0, final_edge_count - initial_edge_count)
    experiment_delta = max(0, final_experiment_count - initial_experiment_count)
    cycle_latencies = [
        float(item.get('pipeline_timings', {}).get('total_runtime_ms', 0.0) or 0.0) / 1000.0
        for item in results
    ]

    capacity_report = {
        'campaigns_per_second': round(len(results) / elapsed, 3),
        'graph_edges_per_second': round(graph_edge_delta / elapsed, 3),
        'experiment_creations_per_second': round(experiment_delta / elapsed, 3),
        'avg_cycle_latency': round(mean(cycle_latencies), 4) if cycle_latencies else 0.0,
        'queue_depth': queue_stats()['queue_depth'],
    }
    print(f'capacity_report = {capacity_report}')

    assert len(results) == 100
    assert capacity_report['campaigns_per_second'] > 0
    assert capacity_report['graph_edges_per_second'] >= 0
    assert capacity_report['avg_cycle_latency'] >= 0


def _accelerate_non_learning_stages(monkeypatch) -> None:
    monkeypatch.setattr(orchestrator, 'assemble_signals', lambda *args, **kwargs: {'avg_rank': 10.0, 'content_count': 5.0, 'technical_issue_count': 1.0, 'local_health': 0.5})
    monkeypatch.setattr(orchestrator, 'write_temporal_signals', lambda *args, **kwargs: {'inserted': 1, 'skipped': 0})
    monkeypatch.setattr(orchestrator, 'compute_features', lambda *args, **kwargs: {'rank_velocity': 0.2, 'content_velocity': 0.1, 'link_velocity': 0.05, 'review_velocity': 0.0})
    monkeypatch.setattr(orchestrator, 'detect_patterns', lambda *args, **kwargs: [])
    monkeypatch.setattr(orchestrator, 'discover_cohort_patterns', lambda *args, **kwargs: [])
    monkeypatch.setattr(orchestrator, 'collect_legacy_diagnostics', lambda *args, **kwargs: [])
    monkeypatch.setattr(orchestrator, 'diagnostics_to_patterns', lambda *args, **kwargs: [])
    monkeypatch.setattr(orchestrator, 'diagnostics_to_policy_inputs', lambda *args, **kwargs: [])
    monkeypatch.setattr(orchestrator, '_select_recommendations_via_digital_twin', _fast_digital_twin_selection)
    monkeypatch.setattr(orchestrator, 'schedule_execution', _fast_schedule_execution)
    monkeypatch.setattr(orchestrator, 'execute_recommendation', _fast_execute_recommendation)
    monkeypatch.setattr(
        orchestrator,
        'compute_campaign_metrics',
        lambda *args, **kwargs: SimpleNamespace(id='benchmark-metric', metric_date=kwargs['metric_date']),
    )


def _benchmark_recommendations(
    db,
    *,
    campaign,
    features,
    direct_patterns,
    cohort_patterns,
    cycle_started_at,
    legacy_patterns=None,
    legacy_policies=None,
):
    del features, direct_patterns, cohort_patterns, cycle_started_at, legacy_patterns, legacy_policies
    existing = (
        db.query(StrategyRecommendation)
        .filter(StrategyRecommendation.campaign_id == campaign.id)
        .order_by(StrategyRecommendation.created_at.desc(), StrategyRecommendation.id.desc())
        .first()
    )
    if existing is not None:
        return [existing]
    recommendation = StrategyRecommendation(
        tenant_id=campaign.tenant_id,
        campaign_id=campaign.id,
        recommendation_type='policy::child-a',
        rationale='Benchmark recommendation for child-a',
        confidence=0.8,
        confidence_score=0.8,
        evidence_json=json.dumps({'policy_id': 'child-a'}, sort_keys=True),
        rollback_plan_json=json.dumps({'steps': ['noop']}, sort_keys=True),
        status=ensure_enum(StrategyRecommendationStatus.APPROVED, StrategyRecommendationStatus),
        idempotency_key=f'benchmark:{campaign.id}:child-a',
        input_hash=sha256(campaign.id.encode('utf-8')).hexdigest(),
        output_hash=sha256(f'{campaign.id}:child-a'.encode('utf-8')).hexdigest(),
        build_hash=sha256(b'benchmark-build').hexdigest(),
    )
    db.add(recommendation)
    db.flush()
    return [recommendation]


def _fast_digital_twin_selection(db, *, campaign_id: str, recommendations: list[StrategyRecommendation]):
    del db, campaign_id
    if not recommendations:
        return [], {'status': 'no_recommendations', 'selected_recommendation_ids': []}
    selected = sorted(recommendations, key=lambda row: row.id)[:1]
    return selected, {'status': 'optimized', 'selected_recommendation_ids': [row.id for row in selected]}


def _fast_schedule_execution(recommendation_id: str, db=None):
    recommendation = db.get(StrategyRecommendation, recommendation_id)
    if recommendation is None:
        return None
    execution = RecommendationExecution(
        recommendation_id=recommendation.id,
        campaign_id=recommendation.campaign_id,
        execution_type='create_content_brief',
        execution_payload=json.dumps({'metric_name': 'avg_rank', 'metric_before': 100.0}, sort_keys=True),
        idempotency_key=f'benchmark:{recommendation.id}',
        deterministic_hash=sha256(recommendation.id.encode('utf-8')).hexdigest(),
        status='scheduled',
        attempt_count=0,
        risk_score=0.1,
        risk_level='low',
        scope_of_change=1,
        historical_success_rate=0.5,
    )
    db.add(execution)
    db.flush()
    return execution


def _fast_execute_recommendation(execution_id: str, db=None, *, dry_run: bool = False):
    del dry_run
    execution = db.get(RecommendationExecution, execution_id)
    if execution is None:
        return None
    execution.status = 'completed'
    execution.executed_at = datetime.now(UTC)
    execution.result_summary = json.dumps({'status': 'completed'}, sort_keys=True)
    db.flush()
    record_execution_outcome(db, execution=execution, metric_before=100.0, metric_after=105.0)
    db.flush()
    return execution


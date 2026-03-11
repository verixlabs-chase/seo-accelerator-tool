from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from statistics import mean
from time import perf_counter, sleep
from types import SimpleNamespace
import uuid

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.middleware.request_throttle import RequestThrottleMiddleware
from app.events import queue as worker_queue
from app.intelligence import intelligence_orchestrator as orchestrator
from app.intelligence.knowledge_graph.update_engine import flush_graph_write_batch, update_global_knowledge_graph
from app.models.campaign import Campaign



@pytest.mark.parametrize('campaign_count', [100, 500, 1000])
def test_platform_capacity_benchmark(db_session, create_test_org, monkeypatch, campaign_count: int) -> None:
    org = create_test_org(name=f'Benchmark Org {campaign_count}')
    campaigns = [
        Campaign(
            tenant_id=org.id,
            organization_id=org.id,
            name=f'Benchmark Campaign {campaign_count}-{index}',
            domain=f'benchmark-{campaign_count}-{index}.test',
            setup_state='Active',
        )
        for index in range(campaign_count)
    ]
    db_session.add_all(campaigns)
    db_session.commit()

    _install_fast_cycle_monkeypatch(monkeypatch)

    started_at = perf_counter()
    with ThreadPoolExecutor(max_workers=min(64, campaign_count)) as executor:
        futures = [executor.submit(orchestrator.run_campaign_cycle, campaign.id, None) for campaign in campaigns]
        results = [future.result(timeout=30) for future in futures]
    campaign_elapsed = max(perf_counter() - started_at, 1e-6)

    queue_peak_depth = _measure_queue_peak_depth(monkeypatch, campaign_count)
    graph_edges_per_second = _measure_graph_write_rate(db_session, operations=min(campaign_count, 200))
    avg_api_latency = asyncio.run(_measure_api_request_latency(total_requests=min(max(campaign_count // 2, 100), 500)))

    latencies = [float(item['pipeline_timings']['total_runtime_ms']) / 1000.0 for item in results]
    capacity_report = {
        'campaign_count': campaign_count,
        'campaigns_per_second': round(campaign_count / campaign_elapsed, 3),
        'graph_edges_per_second': round(graph_edges_per_second, 3),
        'queue_peak_depth': int(queue_peak_depth),
        'avg_cycle_latency': round(mean(latencies), 4),
        'api_request_latency': round(avg_api_latency, 4),
    }
    print(f'capacity_report = {capacity_report}')

    assert len(results) == campaign_count
    assert all(item.get('campaign_id') for item in results)
    assert capacity_report['campaigns_per_second'] > 0
    assert capacity_report['graph_edges_per_second'] > 0
    assert capacity_report['queue_peak_depth'] >= 0
    assert capacity_report['avg_cycle_latency'] >= 0
    assert capacity_report['api_request_latency'] >= 0


def _install_fast_cycle_monkeypatch(monkeypatch) -> None:
    monkeypatch.setattr(orchestrator, 'assemble_signals', lambda *args, **kwargs: [{'signal': 'ok'}])
    monkeypatch.setattr(orchestrator, 'write_temporal_signals', lambda *args, **kwargs: {'inserted': 1, 'skipped': 0})
    monkeypatch.setattr(orchestrator, 'compute_features', lambda *args, **kwargs: {'rank_velocity': 1.0})
    monkeypatch.setattr(orchestrator, 'detect_patterns', lambda *args, **kwargs: [])
    monkeypatch.setattr(orchestrator, 'discover_cohort_patterns', lambda *args, **kwargs: [])
    monkeypatch.setattr(orchestrator, 'collect_legacy_diagnostics', lambda *args, **kwargs: [])
    monkeypatch.setattr(orchestrator, 'diagnostics_to_patterns', lambda *args, **kwargs: [])
    monkeypatch.setattr(orchestrator, 'diagnostics_to_policy_inputs', lambda *args, **kwargs: [])
    monkeypatch.setattr(orchestrator, '_generate_and_persist_recommendations', lambda *args, **kwargs: [])
    monkeypatch.setattr(orchestrator, '_schedule_recommendation_executions', lambda *args, **kwargs: [])
    monkeypatch.setattr(orchestrator, '_execute_scheduled_executions', lambda *args, **kwargs: [])
    monkeypatch.setattr(
        orchestrator,
        'compute_campaign_metrics',
        lambda *args, **kwargs: SimpleNamespace(id=f"metric-{uuid.uuid4().hex[:8]}", metric_date=kwargs['metric_date']),
    )


def _measure_queue_peak_depth(monkeypatch, campaign_count: int) -> int:
    worker_queue.reset_queue_state()
    peak_depth = 0
    original_sync = worker_queue._sync_metrics

    def tracked_sync() -> None:
        nonlocal peak_depth
        stats = worker_queue.queue_stats()['queue_depth']
        peak_depth = max(peak_depth, max(stats.values(), default=0))
        original_sync()

    monkeypatch.setattr(worker_queue, 'get_settings', lambda: SimpleNamespace(app_env='test', max_queue_depth=10000, max_worker_inflight=2000))
    monkeypatch.setattr(worker_queue, '_RETRY_BACKOFF_SECONDS', (0.0,))
    monkeypatch.setattr(worker_queue, '_sync_metrics', tracked_sync)
    monkeypatch.setattr(worker_queue, '_run_inline', lambda worker_name, payload: _sleep_then_return(worker_name, payload))

    with ThreadPoolExecutor(max_workers=min(64, campaign_count)) as executor:
        futures = [
            executor.submit(worker_queue.dispatch_worker_job, 'experiment', {'event_id': f'evt-{index}'})
            for index in range(campaign_count)
        ]
        for future in futures:
            future.result(timeout=30)

    return peak_depth


def _sleep_then_return(worker_name: str, payload: dict[str, object]) -> dict[str, object]:
    sleep(0.002)
    return {'worker': worker_name, 'payload': payload}


def _measure_graph_write_rate(db_session, *, operations: int) -> float:
    started_at = perf_counter()
    for index in range(operations):
        update_global_knowledge_graph(
            db_session,
            policy_id=f'benchmark-policy-{index}',
            feature_key=f'benchmark-feature-{index % 10}',
            outcome_key='outcome::success',
            industry='benchmark',
            effect_size=0.25,
            confidence=0.75,
            sample_size=5,
        )
    flush_graph_write_batch(db_session, force=True)
    db_session.commit()
    elapsed = max(perf_counter() - started_at, 1e-6)
    return (operations * 3) / elapsed


async def _measure_api_request_latency(*, total_requests: int) -> float:
    app = FastAPI()
    app.add_middleware(RequestThrottleMiddleware, max_concurrent_requests=2000, max_requests_per_tenant=200)

    @app.get('/benchmark')
    async def benchmark() -> dict[str, str]:
        await asyncio.sleep(0.001)
        return {'status': 'ok'}

    latencies: list[float] = []
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://testserver') as client:
        async def issue_request(index: int) -> None:
            started_at = perf_counter()
            response = await client.get('/benchmark', headers={'X-Tenant-Id': f'tenant-{index % 5}'})
            latencies.append(perf_counter() - started_at)
            assert response.status_code in {200, 429}

        await asyncio.gather(*(issue_request(index) for index in range(total_requests)))

    return mean(latencies) if latencies else 0.0


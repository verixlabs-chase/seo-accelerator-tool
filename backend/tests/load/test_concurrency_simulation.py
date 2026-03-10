from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.middleware.request_throttle import RequestThrottleMiddleware
from app.events import queue as worker_queue
from app.intelligence.intelligence_orchestrator import run_campaign_cycle, _campaign_execution_lock


@pytest.mark.anyio
async def test_request_throttle_rejects_when_concurrency_is_exceeded() -> None:
    app = FastAPI()
    app.add_middleware(RequestThrottleMiddleware, max_concurrent_requests=1, max_requests_per_tenant=1)

    @app.get('/probe')
    async def probe() -> dict[str, str]:
        await asyncio.sleep(0.05)
        return {'status': 'ok'}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://testserver') as client:
        first = asyncio.create_task(client.get('/probe', headers={'X-Tenant-Id': 'tenant-a'}))
        await asyncio.sleep(0.005)
        second = await client.get('/probe', headers={'X-Tenant-Id': 'tenant-a'})
        first_response = await first

    assert first_response.status_code == 200
    assert second.status_code == 429


def test_queue_backpressure_rejects_spikes(monkeypatch) -> None:
    worker_queue.reset_queue_state()
    monkeypatch.setattr(
        worker_queue,
        'get_settings',
        lambda: SimpleNamespace(app_env='test', max_queue_depth=1, max_worker_inflight=1),
    )
    monkeypatch.setattr(worker_queue, '_RETRY_BACKOFF_SECONDS', (0.0,))
    worker_queue._QUEUE_DEPTH['experiment'] = 1

    result = worker_queue.dispatch_worker_job('experiment', {'event_id': 'evt-1'})

    assert result['status'] == 'failed'
    assert result['error'] == 'backpressure_limit_exceeded'


def test_campaign_execution_lock_defers_duplicate_cycles() -> None:
    campaign_id = 'campaign-under-load'
    lock = _campaign_execution_lock(campaign_id)
    assert lock.acquire(blocking=False) is True
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(run_campaign_cycle, campaign_id, None)
            result = future.result(timeout=2)
    finally:
        lock.release()

    assert result['campaign_id'] == campaign_id
    assert result['status'] == 'deferred'
    assert result['reason'] == 'campaign_cycle_already_running'

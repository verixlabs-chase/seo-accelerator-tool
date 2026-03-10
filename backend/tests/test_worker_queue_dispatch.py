from __future__ import annotations

from app.events import EventType
from app.events.queue import enqueue_event


def test_enqueue_event_routes_outcome_recorded_to_learning_worker(monkeypatch) -> None:
    calls: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr('app.events.queue.dispatch_worker_job', lambda worker_name, payload: calls.append((worker_name, payload)) or {'worker': worker_name, 'status': 'queued'})

    result = enqueue_event(EventType.OUTCOME_RECORDED.value, {'campaign_id': 'c1'})

    assert result['worker'] == 'learning'
    assert calls == [('learning', {'campaign_id': 'c1'})]


def test_enqueue_event_routes_experiment_completed_to_experiment_worker(monkeypatch) -> None:
    calls: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr('app.events.queue.dispatch_worker_job', lambda worker_name, payload: calls.append((worker_name, payload)) or {'worker': worker_name, 'status': 'queued'})

    result = enqueue_event(EventType.EXPERIMENT_COMPLETED.value, {'policy_id': 'p1'})

    assert result['worker'] == 'experiment'
    assert calls == [('experiment', {'policy_id': 'p1'})]

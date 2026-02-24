from types import SimpleNamespace

from app.core.metrics import active_workers, queue_depth, render_metrics, tasks_in_progress
from app.services import infra_service
from app.tasks import tasks
from app.tasks import celery_app as celery_module


def test_celery_prefetch_multiplier_defaults_by_worker_profile(monkeypatch):
    monkeypatch.delenv("CELERY_WORKER_PREFETCH_MULTIPLIER", raising=False)

    monkeypatch.setenv("CELERY_WORKER_PROFILE", "crawl")
    assert celery_module._resolve_prefetch_multiplier(9) == 1

    monkeypatch.setenv("CELERY_WORKER_PROFILE", "rank")
    assert celery_module._resolve_prefetch_multiplier(9) == 1

    monkeypatch.setenv("CELERY_WORKER_PROFILE", "content")
    assert celery_module._resolve_prefetch_multiplier(9) == 2

    monkeypatch.setenv("CELERY_WORKER_PROFILE", "authority")
    assert celery_module._resolve_prefetch_multiplier(9) == 1


def test_celery_prefetch_multiplier_honors_explicit_override(monkeypatch):
    monkeypatch.setenv("CELERY_WORKER_PREFETCH_MULTIPLIER", "4")
    monkeypatch.setenv("CELERY_WORKER_PROFILE", "content")
    assert celery_module._resolve_prefetch_multiplier(1) == 4


def test_celery_app_config_sets_prefetch_multiplier(monkeypatch):
    monkeypatch.delenv("CELERY_WORKER_PREFETCH_MULTIPLIER", raising=False)
    monkeypatch.setenv("CELERY_WORKER_PROFILE", "content")
    app = celery_module.create_celery_app()
    assert int(app.conf.worker_prefetch_multiplier) == 2


def test_task_execution_regression_smoke():
    result = tasks.ops_healthcheck_snapshot.delay().get()
    assert result["status"] == "ok"


def test_autoscaling_metrics_registered():
    payload, _content_type = render_metrics()
    text = payload.decode("utf-8")
    assert "queue_depth" in text
    assert "active_workers" in text
    assert "tasks_in_progress" in text


def test_queue_and_worker_metrics_update(monkeypatch):
    class _FakeInspector:
        @staticmethod
        def active_queues():
            return {
                "worker-a": [{"name": "crawl_queue"}, {"name": "default_queue"}],
                "worker-b": [{"name": "crawl_queue"}],
            }

    monkeypatch.setattr("app.tasks.celery_app.celery_app.control.inspect", lambda timeout=0.5: _FakeInspector())
    status = infra_service.celery_queue_status()
    assert status["worker_count_per_queue"]["crawl_queue"] == 2
    assert active_workers.labels(queue_name="crawl_queue")._value.get() == 2  # noqa: SLF001

    monkeypatch.setattr("app.services.infra_service._run_redis_probe_value", lambda probe, default: 7)
    depth = infra_service.queue_depth_count("crawl_queue")
    assert depth == 7
    assert queue_depth.labels(queue_name="crawl_queue")._value.get() == 7  # noqa: SLF001


def test_tasks_in_progress_metric_updates():
    before = tasks_in_progress.labels(queue_name="crawl_queue")._value.get()  # noqa: SLF001
    celery_module._record_task_start(task_id="task-1", task=SimpleNamespace(name="crawl.schedule_campaign"))
    during = tasks_in_progress.labels(queue_name="crawl_queue")._value.get()  # noqa: SLF001
    celery_module._record_task_duration(task_id="task-1", task=SimpleNamespace(name="crawl.schedule_campaign"))
    after = tasks_in_progress.labels(queue_name="crawl_queue")._value.get()  # noqa: SLF001
    assert during == before + 1
    assert after == before

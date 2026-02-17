from types import SimpleNamespace

from app.tasks import tasks


def test_task_failure_payload_includes_dead_letter_metadata():
    fake_task = SimpleNamespace(request=SimpleNamespace(retries=3), max_retries=3)
    payload = tasks._task_failure_payload(fake_task, TimeoutError("timed out"))  # type: ignore[arg-type]
    assert payload["retryable"] is True
    assert payload["dead_letter"] is True
    assert payload["current_retry"] == 3
    assert payload["max_retries"] == 3

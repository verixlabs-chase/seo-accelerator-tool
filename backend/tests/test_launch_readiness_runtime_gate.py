from __future__ import annotations

from types import SimpleNamespace

from app.services import launch_readiness_service


def _settings(*, rate_limit_enabled: bool) -> SimpleNamespace:
    return SimpleNamespace(
        app_env="production",
        database_rls_enabled=True,
        rate_limit_enabled=rate_limit_enabled,
    )


def test_runtime_gate_does_not_probe_rate_limit_store_when_disabled(monkeypatch) -> None:
    monkeypatch.setattr(
        launch_readiness_service,
        "get_settings",
        lambda: _settings(rate_limit_enabled=False),
    )
    monkeypatch.setattr(
        launch_readiness_service.infra_service,
        "redis_connected",
        lambda: (_ for _ in ()).throw(AssertionError("disabled rate limiting must not probe Redis")),
    )
    monkeypatch.setattr(
        launch_readiness_service.infra_service,
        "worker_active",
        lambda: (_ for _ in ()).throw(AssertionError("disabled storage must not probe workers")),
    )
    monkeypatch.setattr(
        launch_readiness_service.infra_service,
        "scheduler_active",
        lambda: (_ for _ in ()).throw(AssertionError("disabled storage must not probe scheduler")),
    )

    item = launch_readiness_service._runtime_gate()

    assert item["state"] == launch_readiness_service.BLOCKER
    assert "request rate limiting" in item["next_action"]
    assert item["facts"]["request_rate_limiting"] is False
    assert item["facts"]["rate_limit_store_connected"] is False
    assert item["facts"]["async_checks_performed"] is False


def test_runtime_gate_blocks_when_rate_limit_store_is_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(
        launch_readiness_service,
        "get_settings",
        lambda: _settings(rate_limit_enabled=True),
    )
    monkeypatch.setattr(
        launch_readiness_service.infra_service,
        "redis_connected",
        lambda: False,
    )
    monkeypatch.setattr(
        launch_readiness_service.infra_service,
        "worker_active",
        lambda: (_ for _ in ()).throw(AssertionError("unavailable storage must not probe workers")),
    )
    monkeypatch.setattr(
        launch_readiness_service.infra_service,
        "scheduler_active",
        lambda: (_ for _ in ()).throw(AssertionError("unavailable storage must not probe scheduler")),
    )

    item = launch_readiness_service._runtime_gate()

    assert item["state"] == launch_readiness_service.BLOCKER
    assert "request rate-limit storage" in item["next_action"]
    assert item["facts"]["request_rate_limiting"] is True
    assert item["facts"]["rate_limit_store_connected"] is False
    assert item["facts"]["async_checks_performed"] is False


def test_runtime_gate_blocks_when_background_worker_is_inactive(monkeypatch) -> None:
    monkeypatch.setattr(
        launch_readiness_service,
        "get_settings",
        lambda: _settings(rate_limit_enabled=True),
    )
    monkeypatch.setattr(launch_readiness_service.infra_service, "redis_connected", lambda: True)
    monkeypatch.setattr(launch_readiness_service.infra_service, "worker_active", lambda: False)
    monkeypatch.setattr(launch_readiness_service.infra_service, "scheduler_active", lambda: True)

    item = launch_readiness_service._runtime_gate()

    assert item["state"] == launch_readiness_service.BLOCKER
    assert "background worker heartbeat" in item["next_action"]
    assert item["facts"]["async_checks_performed"] is True
    assert item["facts"]["background_worker_active"] is False
    assert item["facts"]["scheduler_active"] is True


def test_runtime_gate_blocks_when_scheduler_is_inactive(monkeypatch) -> None:
    monkeypatch.setattr(
        launch_readiness_service,
        "get_settings",
        lambda: _settings(rate_limit_enabled=True),
    )
    monkeypatch.setattr(launch_readiness_service.infra_service, "redis_connected", lambda: True)
    monkeypatch.setattr(launch_readiness_service.infra_service, "worker_active", lambda: True)
    monkeypatch.setattr(launch_readiness_service.infra_service, "scheduler_active", lambda: False)

    item = launch_readiness_service._runtime_gate()

    assert item["state"] == launch_readiness_service.BLOCKER
    assert "scheduler heartbeat" in item["next_action"]
    assert item["facts"]["background_worker_active"] is True
    assert item["facts"]["scheduler_active"] is False


def test_runtime_gate_passes_only_with_connected_rate_limit_store(monkeypatch) -> None:
    monkeypatch.setattr(
        launch_readiness_service,
        "get_settings",
        lambda: _settings(rate_limit_enabled=True),
    )
    monkeypatch.setattr(
        launch_readiness_service.infra_service,
        "redis_connected",
        lambda: True,
    )
    monkeypatch.setattr(launch_readiness_service.infra_service, "worker_active", lambda: True)
    monkeypatch.setattr(launch_readiness_service.infra_service, "scheduler_active", lambda: True)

    item = launch_readiness_service._runtime_gate()

    assert item["state"] == launch_readiness_service.PASS
    assert item["facts"] == {
        "production_runtime": True,
        "database_tenant_isolation": True,
        "request_rate_limiting": True,
        "rate_limit_store_connected": True,
        "async_checks_performed": True,
        "background_worker_active": True,
        "scheduler_active": True,
    }

from __future__ import annotations

from types import SimpleNamespace

from app.services import launch_readiness_service


def _settings(
    *,
    rate_limit_enabled: bool,
    hosted_serverless: bool = True,
) -> SimpleNamespace:
    return SimpleNamespace(
        app_env="production",
        database_rls_enabled=True,
        rate_limit_enabled=rate_limit_enabled,
        rate_limit_backend="postgres",
        hosted_serverless=hosted_serverless,
    )


def _must_not_run(name: str):
    return lambda: (_ for _ in ()).throw(AssertionError(f"must not call {name}"))


def test_runtime_gate_does_not_probe_disabled_rate_limit_or_hosted_async_runtime(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        launch_readiness_service,
        "get_settings",
        lambda: _settings(rate_limit_enabled=False),
    )
    monkeypatch.setattr(
        launch_readiness_service.infra_service,
        "rate_limit_store_connected",
        _must_not_run("rate-limit store"),
    )
    for probe in ("redis_connected", "worker_active", "scheduler_active"):
        monkeypatch.setattr(
            launch_readiness_service.infra_service,
            probe,
            _must_not_run(probe),
        )

    item = launch_readiness_service._runtime_gate()

    assert item["state"] == launch_readiness_service.BLOCKER
    assert "request rate limiting" in item["next_action"]
    assert item["facts"]["request_rate_limiting"] is False
    assert item["facts"]["rate_limit_store_connected"] is False
    assert item["facts"]["rate_limit_backend"] == "postgres"
    assert item["facts"]["hosted_serverless"] is True
    assert item["facts"]["async_checks_performed"] is False


def test_runtime_gate_blocks_when_database_rate_limit_store_is_unavailable(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        launch_readiness_service,
        "get_settings",
        lambda: _settings(rate_limit_enabled=True),
    )
    monkeypatch.setattr(
        launch_readiness_service.infra_service,
        "rate_limit_store_connected",
        lambda: False,
    )
    for probe in ("redis_connected", "worker_active", "scheduler_active"):
        monkeypatch.setattr(
            launch_readiness_service.infra_service,
            probe,
            _must_not_run(probe),
        )

    item = launch_readiness_service._runtime_gate()

    assert item["state"] == launch_readiness_service.BLOCKER
    assert "request rate-limit storage" in item["next_action"]
    assert item["facts"]["request_rate_limiting"] is True
    assert item["facts"]["rate_limit_store_connected"] is False
    assert item["facts"]["async_checks_performed"] is False


def test_hosted_runtime_gate_passes_without_redis_worker_or_scheduler(monkeypatch) -> None:
    monkeypatch.setattr(
        launch_readiness_service,
        "get_settings",
        lambda: _settings(rate_limit_enabled=True),
    )
    monkeypatch.setattr(
        launch_readiness_service.infra_service,
        "rate_limit_store_connected",
        lambda: True,
    )
    for probe in ("redis_connected", "worker_active", "scheduler_active"):
        monkeypatch.setattr(
            launch_readiness_service.infra_service,
            probe,
            _must_not_run(probe),
        )

    item = launch_readiness_service._runtime_gate()

    assert item["state"] == launch_readiness_service.PASS
    assert item["facts"] == {
        "production_runtime": True,
        "database_tenant_isolation": True,
        "request_rate_limiting": True,
        "rate_limit_backend": "postgres",
        "rate_limit_store_connected": True,
        "hosted_serverless": True,
        "async_checks_performed": False,
        "async_store_connected": False,
        "background_worker_active": False,
        "scheduler_active": False,
    }


def test_nonhosted_runtime_gate_blocks_when_async_redis_is_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(
        launch_readiness_service,
        "get_settings",
        lambda: _settings(rate_limit_enabled=True, hosted_serverless=False),
    )
    monkeypatch.setattr(
        launch_readiness_service.infra_service,
        "rate_limit_store_connected",
        lambda: True,
    )
    monkeypatch.setattr(launch_readiness_service.infra_service, "redis_connected", lambda: False)
    monkeypatch.setattr(
        launch_readiness_service.infra_service,
        "worker_active",
        _must_not_run("worker_active"),
    )
    monkeypatch.setattr(
        launch_readiness_service.infra_service,
        "scheduler_active",
        _must_not_run("scheduler_active"),
    )

    item = launch_readiness_service._runtime_gate()

    assert item["state"] == launch_readiness_service.BLOCKER
    assert "Redis async runtime" in item["next_action"]
    assert "background worker heartbeat" in item["next_action"]
    assert "scheduler heartbeat" in item["next_action"]
    assert item["facts"]["rate_limit_store_connected"] is True
    assert item["facts"]["async_store_connected"] is False


def test_nonhosted_runtime_gate_blocks_when_background_worker_is_inactive(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        launch_readiness_service,
        "get_settings",
        lambda: _settings(rate_limit_enabled=True, hosted_serverless=False),
    )
    monkeypatch.setattr(
        launch_readiness_service.infra_service,
        "rate_limit_store_connected",
        lambda: True,
    )
    monkeypatch.setattr(launch_readiness_service.infra_service, "redis_connected", lambda: True)
    monkeypatch.setattr(launch_readiness_service.infra_service, "worker_active", lambda: False)
    monkeypatch.setattr(launch_readiness_service.infra_service, "scheduler_active", lambda: True)

    item = launch_readiness_service._runtime_gate()

    assert item["state"] == launch_readiness_service.BLOCKER
    assert "background worker heartbeat" in item["next_action"]
    assert item["facts"]["async_store_connected"] is True
    assert item["facts"]["background_worker_active"] is False
    assert item["facts"]["scheduler_active"] is True


def test_nonhosted_runtime_gate_blocks_when_scheduler_is_inactive(monkeypatch) -> None:
    monkeypatch.setattr(
        launch_readiness_service,
        "get_settings",
        lambda: _settings(rate_limit_enabled=True, hosted_serverless=False),
    )
    monkeypatch.setattr(
        launch_readiness_service.infra_service,
        "rate_limit_store_connected",
        lambda: True,
    )
    monkeypatch.setattr(launch_readiness_service.infra_service, "redis_connected", lambda: True)
    monkeypatch.setattr(launch_readiness_service.infra_service, "worker_active", lambda: True)
    monkeypatch.setattr(launch_readiness_service.infra_service, "scheduler_active", lambda: False)

    item = launch_readiness_service._runtime_gate()

    assert item["state"] == launch_readiness_service.BLOCKER
    assert "scheduler heartbeat" in item["next_action"]
    assert item["facts"]["background_worker_active"] is True
    assert item["facts"]["scheduler_active"] is False


def test_nonhosted_runtime_gate_passes_all_independent_dependency_checks(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        launch_readiness_service,
        "get_settings",
        lambda: _settings(rate_limit_enabled=True, hosted_serverless=False),
    )
    monkeypatch.setattr(
        launch_readiness_service.infra_service,
        "rate_limit_store_connected",
        lambda: True,
    )
    monkeypatch.setattr(launch_readiness_service.infra_service, "redis_connected", lambda: True)
    monkeypatch.setattr(launch_readiness_service.infra_service, "worker_active", lambda: True)
    monkeypatch.setattr(launch_readiness_service.infra_service, "scheduler_active", lambda: True)

    item = launch_readiness_service._runtime_gate()

    assert item["state"] == launch_readiness_service.PASS
    assert item["facts"]["rate_limit_backend"] == "postgres"
    assert item["facts"]["rate_limit_store_connected"] is True
    assert item["facts"]["async_store_connected"] is True
    assert item["facts"]["background_worker_active"] is True
    assert item["facts"]["scheduler_active"] is True

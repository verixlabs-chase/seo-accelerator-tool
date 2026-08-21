from types import SimpleNamespace

from app.api.v1 import health as health_api


def test_health_endpoint(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "ok"
    assert data["rate_limit"] == {
        "enabled": health_api.settings.rate_limit_enabled,
        "backend": health_api.settings.rate_limit_backend,
    }


def test_readiness_endpoint(client):
    response = client.get("/api/v1/health/readiness")
    readiness_status = response.json()["data"]["status"]
    assert response.status_code == (200 if readiness_status == "ready" else 503)
    assert readiness_status in {"ready", "degraded"}
    assert response.headers["cache-control"] == "private, no-store"
    dependencies = response.json()["data"]["dependencies"]
    assert {
        "database",
        "rate_limit_enabled",
        "rate_limit_backend",
        "rate_limit_store",
        "async_runtime_required",
        "redis",
        "worker_heartbeat",
        "scheduler_heartbeat",
    }.issubset(dependencies)


def test_metrics_endpoint(client):
    response = client.get("/api/v1/health/metrics")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["truth_scope"] == {
        "mode": "process_local",
        "durable": False,
        "multi_instance_safe": False,
        "warning": "Metrics are derived from in-memory process state and are not cluster-wide operational truth.",
    }
    assert "slos" in data
    assert "metrics" in data
    assert "alerts" in data
    assert "alert_state" in data
    assert "queue_backlog_tasks" in data["metrics"]


def test_infra_status_endpoint(client, monkeypatch):
    monkeypatch.setattr(
        health_api,
        "settings",
        SimpleNamespace(
            rate_limit_enabled=True,
            rate_limit_backend="postgres",
            hosted_serverless=False,
        ),
    )
    monkeypatch.setattr("app.services.infra_service.rate_limit_store_connected", lambda: True)
    monkeypatch.setattr("app.services.infra_service.redis_connected", lambda: True)
    monkeypatch.setattr("app.services.infra_service.worker_active", lambda: True)
    monkeypatch.setattr("app.services.infra_service.scheduler_active", lambda: False)
    monkeypatch.setattr("app.services.infra_service.db_connected", lambda: True)
    monkeypatch.setattr("app.services.infra_service.proxy_configured", lambda: False)
    monkeypatch.setattr("app.services.infra_service.smtp_configured", lambda: True)

    response = client.get("/api/v1/infra/status")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data == {
        "rate_limit_backend": "postgres",
        "rate_limit_store": "connected",
        "redis": "connected",
        "worker": "active",
        "scheduler": "inactive",
        "db": "connected",
        "proxy": "not configured",
        "smtp": "configured",
    }


def test_readiness_degrades_when_redis_unavailable(client, monkeypatch):
    monkeypatch.setattr(
        health_api,
        "settings",
        SimpleNamespace(
            rate_limit_enabled=True,
            rate_limit_backend="postgres",
            hosted_serverless=False,
        ),
    )
    monkeypatch.setattr("app.services.infra_service.db_connected", lambda: True)
    monkeypatch.setattr("app.services.infra_service.rate_limit_store_connected", lambda: True)
    monkeypatch.setattr("app.services.infra_service.redis_connected", lambda: False)
    monkeypatch.setattr("app.services.infra_service.worker_active", lambda: True)
    monkeypatch.setattr("app.services.infra_service.scheduler_active", lambda: True)

    response = client.get("/api/v1/health/readiness")
    assert response.status_code == 503
    data = response.json()["data"]
    assert data["status"] == "degraded"
    assert data["dependencies"] == {
        "database": True,
        "rate_limit_enabled": True,
        "rate_limit_backend": "postgres",
        "rate_limit_store": True,
        "async_runtime_required": True,
        "redis": False,
        "worker_heartbeat": False,
        "scheduler_heartbeat": False,
    }


def test_infra_status_marks_worker_inactive_when_redis_unavailable(client, monkeypatch):
    monkeypatch.setattr(
        health_api,
        "settings",
        SimpleNamespace(
            rate_limit_enabled=True,
            rate_limit_backend="postgres",
            hosted_serverless=False,
        ),
    )
    monkeypatch.setattr("app.services.infra_service.rate_limit_store_connected", lambda: True)
    monkeypatch.setattr("app.services.infra_service.redis_connected", lambda: False)
    monkeypatch.setattr("app.services.infra_service.worker_active", lambda: True)
    monkeypatch.setattr("app.services.infra_service.scheduler_active", lambda: True)
    monkeypatch.setattr("app.services.infra_service.db_connected", lambda: True)
    monkeypatch.setattr("app.services.infra_service.proxy_configured", lambda: False)
    monkeypatch.setattr("app.services.infra_service.smtp_configured", lambda: True)

    response = client.get("/api/v1/infra/status")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["redis"] == "not connected"
    assert data["worker"] == "inactive"
    assert data["scheduler"] == "inactive"
    assert data["rate_limit_backend"] == "postgres"
    assert data["rate_limit_store"] == "connected"


def test_hosted_readiness_uses_database_limiter_without_async_redis_probes(
    client,
    monkeypatch,
):
    monkeypatch.setattr(
        health_api,
        "settings",
        SimpleNamespace(
            rate_limit_enabled=True,
            rate_limit_backend="postgres",
            hosted_serverless=True,
        ),
    )
    monkeypatch.setattr("app.services.infra_service.db_connected", lambda: True)
    monkeypatch.setattr("app.services.infra_service.rate_limit_store_connected", lambda: True)
    for probe in ("redis_connected", "worker_active", "scheduler_active"):
        monkeypatch.setattr(
            f"app.services.infra_service.{probe}",
            lambda probe=probe: (_ for _ in ()).throw(
                AssertionError(f"hosted readiness must not call {probe}")
            ),
        )

    response = client.get("/api/v1/health/readiness")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "ready"
    assert data["dependencies"] == {
        "database": True,
        "rate_limit_enabled": True,
        "rate_limit_backend": "postgres",
        "rate_limit_store": True,
        "async_runtime_required": False,
        "redis": None,
        "worker_heartbeat": None,
        "scheduler_heartbeat": None,
    }


def test_readiness_degrades_when_database_limiter_probe_fails(client, monkeypatch):
    monkeypatch.setattr(
        health_api,
        "settings",
        SimpleNamespace(
            rate_limit_enabled=True,
            rate_limit_backend="postgres",
            hosted_serverless=True,
        ),
    )
    monkeypatch.setattr("app.services.infra_service.db_connected", lambda: True)
    monkeypatch.setattr("app.services.infra_service.rate_limit_store_connected", lambda: False)

    response = client.get("/api/v1/health/readiness")

    assert response.status_code == 503
    data = response.json()["data"]
    assert data["status"] == "degraded"
    assert data["dependencies"]["database"] is True
    assert data["dependencies"]["rate_limit_store"] is False

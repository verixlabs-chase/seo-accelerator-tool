def test_health_endpoint(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "ok"


def test_readiness_endpoint(client):
    response = client.get("/api/v1/health/readiness")
    assert response.status_code == 200
    assert response.json()["data"]["status"] in {"ready", "degraded"}
    assert "database" in response.json()["data"]["dependencies"]
    assert "redis" in response.json()["data"]["dependencies"]
    assert "worker_heartbeat" in response.json()["data"]["dependencies"]
    assert "scheduler_heartbeat" in response.json()["data"]["dependencies"]


def test_metrics_endpoint(client):
    response = client.get("/api/v1/health/metrics")
    assert response.status_code == 200
    data = response.json()["data"]
    assert "slos" in data
    assert "metrics" in data
    assert "alerts" in data
    assert "alert_state" in data
    assert "queue_backlog_tasks" in data["metrics"]


def test_infra_status_endpoint(client, monkeypatch):
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
        "redis": "connected",
        "worker": "active",
        "scheduler": "inactive",
        "db": "connected",
        "proxy": "not configured",
        "smtp": "configured",
    }


def test_readiness_degrades_when_redis_unavailable(client, monkeypatch):
    monkeypatch.setattr("app.services.infra_service.db_connected", lambda: True)
    monkeypatch.setattr("app.services.infra_service.redis_connected", lambda: False)
    monkeypatch.setattr("app.services.infra_service.worker_active", lambda: True)
    monkeypatch.setattr("app.services.infra_service.scheduler_active", lambda: True)

    response = client.get("/api/v1/health/readiness")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "degraded"
    assert data["dependencies"] == {
        "database": True,
        "redis": False,
        "worker_heartbeat": False,
        "scheduler_heartbeat": False,
    }


def test_infra_status_marks_worker_inactive_when_redis_unavailable(client, monkeypatch):
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

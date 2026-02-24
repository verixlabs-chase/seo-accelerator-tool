from types import SimpleNamespace


def _login(client, email="a@example.com", password="pass-a") -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


def _create_campaign(client, token, name="Backpressure Campaign", domain="backpressure.example") -> dict:
    response = client.post(
        "/api/v1/campaigns",
        json={"name": name, "domain": domain},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    return response.json()["data"]


def test_queue_backpressure_threshold_trigger(monkeypatch):
    monkeypatch.setattr(
        "app.services.infra_service.get_settings",
        lambda: SimpleNamespace(queue_backpressure_enabled=True, queue_backpressure_threshold=100),
    )
    monkeypatch.setattr("app.services.infra_service.queue_depth_count", lambda queue_name: 101)
    from app.services import infra_service

    assert infra_service.queue_backpressure_active("crawl") is True


def test_rank_workload_bypasses_backpressure(monkeypatch):
    monkeypatch.setattr(
        "app.services.infra_service.get_settings",
        lambda: SimpleNamespace(queue_backpressure_enabled=True, queue_backpressure_threshold=1),
    )
    monkeypatch.setattr("app.services.infra_service.queue_depth_count", lambda queue_name: 1000)
    from app.services import infra_service

    assert infra_service.queue_backpressure_active("rank") is False


def test_backpressure_fails_open_when_redis_unavailable(monkeypatch):
    monkeypatch.setattr(
        "app.services.infra_service.get_settings",
        lambda: SimpleNamespace(queue_backpressure_enabled=True, queue_backpressure_threshold=10),
    )
    monkeypatch.setattr("app.services.infra_service.queue_depth_count", lambda queue_name: None)
    from app.services import infra_service

    assert infra_service.queue_backpressure_active("content") is False


def test_crawl_schedule_returns_503_when_backpressure_active(client, monkeypatch):
    token = _login(client)
    campaign = _create_campaign(client, token, name="Crawl Backpressure", domain="crawl-backpressure.example")
    monkeypatch.setattr(
        "app.services.infra_service.queue_backpressure_active",
        lambda workload: workload == "crawl",
    )
    response = client.post(
        "/api/v1/crawl/schedule",
        json={"campaign_id": campaign["id"], "crawl_type": "deep", "seed_url": "https://example.com"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 503
    assert response.json()["error"]["details"]["reason_code"] == "queue_backpressure_active"


def test_content_plan_returns_503_when_backpressure_active(client, monkeypatch):
    token = _login(client)
    campaign = _create_campaign(client, token, name="Content Backpressure", domain="content-backpressure.example")
    monkeypatch.setattr(
        "app.services.infra_service.queue_backpressure_active",
        lambda workload: workload == "content",
    )
    response = client.get(
        f"/api/v1/content/plan?campaign_id={campaign['id']}&month_number=1",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 503
    assert response.json()["error"]["details"]["reason_code"] == "queue_backpressure_active"


def test_rank_schedule_bypasses_backpressure(client, monkeypatch):
    token = _login(client)
    campaign = _create_campaign(client, token, name="Rank Bypass", domain="rank-bypass.example")
    monkeypatch.setattr(
        "app.services.infra_service.queue_backpressure_active",
        lambda workload: workload in {"crawl", "content"},
    )
    response = client.post(
        "/api/v1/rank/schedule",
        json={"campaign_id": campaign["id"], "location_code": "US"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200

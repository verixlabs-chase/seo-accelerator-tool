from app.services import crawl_metrics


def _login(client, email, password):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


def test_crawl_metrics_endpoint(client):
    crawl_metrics.observe("crawl.fetch_batch", duration_ms=1200.0, success=True)
    token = _login(client, "a@example.com", "pass-a")
    response = client.get("/api/v1/crawl/metrics", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    stages = response.json()["data"]["stages"]
    assert "crawl.fetch_batch" in stages
    assert "slo_ok" in stages["crawl.fetch_batch"]


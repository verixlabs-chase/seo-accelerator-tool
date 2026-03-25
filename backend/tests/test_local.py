def _login(client, email, password):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


def test_local_health_and_reviews_velocity(client):
    token = _login(client, "a@example.com", "pass-a")
    campaign = client.post(
        "/api/v1/campaigns",
        json={"name": "Local Campaign", "domain": "local.com"},
        headers={"Authorization": f"Bearer {token}"},
    ).json()["data"]

    health = client.get(
        f"/api/v1/local/health?campaign_id={campaign['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert health.status_code == 200
    assert "health_score" in health.json()["data"]
    assert health.json()["data"]["truth"]["classification"] in {"synthetic", "in_progress"}

    map_pack = client.get(
        f"/api/v1/local/map-pack?campaign_id={campaign['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert map_pack.status_code == 200
    assert "map_pack_position" in map_pack.json()["data"]
    assert map_pack.json()["data"]["truth"]["classification"] == "synthetic"

    reviews = client.get(
        f"/api/v1/reviews?campaign_id={campaign['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert reviews.status_code == 200
    assert len(reviews.json()["data"]["items"]) >= 1
    assert reviews.json()["data"]["truth"]["classification"] in {"synthetic", "in_progress"}

    velocity = client.get(
        f"/api/v1/reviews/velocity?campaign_id={campaign['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert velocity.status_code == 200
    assert "reviews_last_30d" in velocity.json()["data"]
    assert "avg_rating_last_30d" in velocity.json()["data"]
    assert velocity.json()["data"]["truth"]["classification"] in {"synthetic", "in_progress"}

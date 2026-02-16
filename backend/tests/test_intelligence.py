def _login(client, email, password):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


def test_intelligence_score_recommendations_and_advance_month(client):
    token = _login(client, "a@example.com", "pass-a")
    campaign = client.post(
        "/api/v1/campaigns",
        json={"name": "Intelligence Campaign", "domain": "intel.com"},
        headers={"Authorization": f"Bearer {token}"},
    ).json()["data"]

    score = client.get(
        f"/api/v1/intelligence/score?campaign_id={campaign['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert score.status_code == 200
    assert "score_value" in score.json()["data"]

    recs = client.get(
        f"/api/v1/intelligence/recommendations?campaign_id={campaign['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert recs.status_code == 200
    assert len(recs.json()["data"]["items"]) >= 1

    blocked = client.post(
        f"/api/v1/campaigns/{campaign['id']}/advance-month",
        json={"override": False},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert blocked.status_code == 400

    advanced = client.post(
        f"/api/v1/campaigns/{campaign['id']}/advance-month",
        json={"override": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert advanced.status_code == 200
    assert advanced.json()["data"]["advanced_to_month"] == 2


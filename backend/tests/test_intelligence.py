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
    items = recs.json()["data"]["items"]
    assert len(items) >= 1
    first = items[0]
    assert "confidence_score" in first
    assert isinstance(first["confidence_score"], float)
    assert 0.0 <= first["confidence_score"] <= 1.0
    assert "evidence" in first
    assert isinstance(first["evidence"], list)
    assert len(first["evidence"]) >= 1
    assert "risk_tier" in first
    assert isinstance(first["risk_tier"], int)
    assert 0 <= first["risk_tier"] <= 4
    assert "rollback_plan" in first
    assert isinstance(first["rollback_plan"], dict)
    assert len(first["rollback_plan"]) >= 1

    recommendation_id = first["id"]
    invalid = client.post(
        f"/api/v1/intelligence/recommendations/{recommendation_id}/transition?campaign_id={campaign['id']}",
        json={"target_state": "APPROVED"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert invalid.status_code == 400

    validated = client.post(
        f"/api/v1/intelligence/recommendations/{recommendation_id}/transition?campaign_id={campaign['id']}",
        json={"target_state": "VALIDATED"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert validated.status_code == 200
    assert validated.json()["data"]["status"] == "VALIDATED"

    approved = client.post(
        f"/api/v1/intelligence/recommendations/{recommendation_id}/transition?campaign_id={campaign['id']}",
        json={"target_state": "APPROVED"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert approved.status_code == 200
    assert approved.json()["data"]["status"] == "APPROVED"

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

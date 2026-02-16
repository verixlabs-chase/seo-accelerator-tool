def _login(client, email, password):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


def test_campaigns_are_tenant_isolated(client):
    token_a = _login(client, "a@example.com", "pass-a")
    token_b = _login(client, "b@example.com", "pass-b")

    create_a = client.post(
        "/api/v1/campaigns",
        json={"name": "A Campaign", "domain": "a.com"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert create_a.status_code == 200

    create_b = client.post(
        "/api/v1/campaigns",
        json={"name": "B Campaign", "domain": "b.com"},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert create_b.status_code == 200

    list_a = client.get("/api/v1/campaigns", headers={"Authorization": f"Bearer {token_a}"})
    list_b = client.get("/api/v1/campaigns", headers={"Authorization": f"Bearer {token_b}"})
    assert len(list_a.json()["data"]["items"]) == 1
    assert len(list_b.json()["data"]["items"]) == 1
    assert list_a.json()["data"]["items"][0]["domain"] == "a.com"
    assert list_b.json()["data"]["items"][0]["domain"] == "b.com"


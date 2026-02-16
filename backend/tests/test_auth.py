def test_login_and_refresh_and_me(client):
    login_res = client.post("/api/v1/auth/login", json={"email": "a@example.com", "password": "pass-a"})
    assert login_res.status_code == 200
    payload = login_res.json()["data"]
    assert payload["token_type"] == "bearer"
    assert payload["user"]["roles"] == ["tenant_admin"]

    me_res = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {payload['access_token']}"})
    assert me_res.status_code == 200
    assert me_res.json()["data"]["tenant_id"] == payload["user"]["tenant_id"]

    refresh_res = client.post("/api/v1/auth/refresh", json={"refresh_token": payload["refresh_token"]})
    assert refresh_res.status_code == 200
    assert refresh_res.json()["data"]["access_token"]


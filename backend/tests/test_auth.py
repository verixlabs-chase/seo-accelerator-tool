def test_login_and_refresh_and_me(client):
    login_res = client.post("/api/v1/auth/login", json={"email": "a@example.com", "password": "pass-a"})
    assert login_res.status_code == 200
    payload = login_res.json()["data"]
    assert payload["token_type"] == "bearer"
    assert payload["user"]["org_role"] == "org_admin"
    assert "tenant_admin" in payload["user"]["roles"]

    me_res = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {payload['access_token']}"})
    assert me_res.status_code == 200
    assert me_res.json()["data"]["organization_id"] == payload["user"]["organization_id"]

    refresh_res = client.post("/api/v1/auth/refresh", json={"refresh_token": payload["refresh_token"]})
    assert refresh_res.status_code == 200
    assert refresh_res.json()["data"]["access_token"]


def test_refresh_tokens_rotate_and_cannot_be_replayed(client):
    login_res = client.post("/api/v1/auth/login", json={"email": "a@example.com", "password": "pass-a"})
    assert login_res.status_code == 200
    original_refresh = login_res.json()["data"]["refresh_token"]

    rotated = client.post("/api/v1/auth/refresh", json={"refresh_token": original_refresh})
    assert rotated.status_code == 200
    rotated_payload = rotated.json()["data"]
    assert rotated_payload["refresh_token"] != original_refresh

    replay = client.post("/api/v1/auth/refresh", json={"refresh_token": original_refresh})
    assert replay.status_code == 401
    assert "rotated" in str(replay.json()).lower()

    second_rotation = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": rotated_payload["refresh_token"]},
    )
    assert second_rotation.status_code == 200


def test_logout_revokes_access_and_refresh_session(client):
    login_res = client.post("/api/v1/auth/login", json={"email": "a@example.com", "password": "pass-a"})
    payload = login_res.json()["data"]
    headers = {"Authorization": f"Bearer {payload['access_token']}"}

    sessions = client.get("/api/v1/auth/sessions", headers=headers)
    assert sessions.status_code == 200
    assert len(sessions.json()["data"]["sessions"]) == 1

    logout = client.post("/api/v1/auth/logout", headers=headers)
    assert logout.status_code == 200
    assert logout.json()["data"]["session_revoked"] is True

    me_after_logout = client.get("/api/v1/auth/me", headers=headers)
    assert me_after_logout.status_code == 401

    refresh_after_logout = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": payload["refresh_token"]},
    )
    assert refresh_after_logout.status_code == 401

def test_login_sets_http_only_auth_cookies_and_me_uses_cookie_session(client):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "a@example.com", "password": "pass-a"},
    )
    assert response.status_code == 200
    set_cookie_headers = response.headers.get_list("set-cookie")
    assert any("lsos_access_token=" in header and "HttpOnly" in header for header in set_cookie_headers)
    assert any("lsos_refresh_token=" in header and "HttpOnly" in header for header in set_cookie_headers)

    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["data"]["id"]


def test_refresh_and_logout_use_cookie_session_without_body_token(client):
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "a@example.com", "password": "pass-a"},
    )
    assert login.status_code == 200

    refreshed = client.post("/api/v1/auth/refresh")
    assert refreshed.status_code == 200
    refresh_set_cookie_headers = refreshed.headers.get_list("set-cookie")
    assert any("lsos_access_token=" in header for header in refresh_set_cookie_headers)

    logout = client.post("/api/v1/auth/logout")
    assert logout.status_code == 200
    logout_set_cookie_headers = logout.headers.get_list("set-cookie")
    assert any("lsos_access_token=" in header.lower() and "max-age=0" in header.lower() for header in logout_set_cookie_headers)
    assert any("lsos_refresh_token=" in header.lower() and "max-age=0" in header.lower() for header in logout_set_cookie_headers)

    me = client.get("/api/v1/auth/me")
    assert me.status_code == 401

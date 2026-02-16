def _login(client, email, password):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


def test_reports_generate_list_get_and_deliver(client):
    token = _login(client, "a@example.com", "pass-a")
    campaign = client.post(
        "/api/v1/campaigns",
        json={"name": "Reporting Campaign", "domain": "reports.com"},
        headers={"Authorization": f"Bearer {token}"},
    ).json()["data"]

    generated = client.post(
        "/api/v1/reports/generate",
        json={"campaign_id": campaign["id"], "month_number": 1},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert generated.status_code == 200
    report_id = generated.json()["data"]["id"]

    listed = client.get("/api/v1/reports", headers={"Authorization": f"Bearer {token}"})
    assert listed.status_code == 200
    assert len(listed.json()["data"]["items"]) >= 1

    detail = client.get(f"/api/v1/reports/{report_id}", headers={"Authorization": f"Bearer {token}"})
    assert detail.status_code == 200
    assert len(detail.json()["data"]["artifacts"]) >= 1

    delivered = client.post(
        f"/api/v1/reports/{report_id}/deliver",
        json={"recipient": "owner@example.com"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert delivered.status_code == 200
    assert delivered.json()["data"]["delivery_status"] == "sent"


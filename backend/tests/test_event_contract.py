import json

from app.models.audit_log import AuditLog


def _login(client, email, password):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


def test_recommendation_generation_emits_contract_event(client, db_session):
    token = _login(client, "a@example.com", "pass-a")
    headers = {"Authorization": f"Bearer {token}"}

    campaign = client.post(
        "/api/v1/campaigns",
        json={"name": "Event Campaign", "domain": "events.com"},
        headers=headers,
    ).json()["data"]

    response = client.get(
        f"/api/v1/intelligence/recommendations?campaign_id={campaign['id']}",
        headers=headers,
    )
    assert response.status_code == 200

    rows = (
        db_session.query(AuditLog)
        .filter(AuditLog.tenant_id == campaign["tenant_id"], AuditLog.event_type == "recommendation.generated")
        .all()
    )
    assert len(rows) >= 1
    payload = json.loads(rows[0].payload_json)
    for field in ("event_id", "tenant_id", "event_type", "timestamp", "payload"):
        assert field in payload

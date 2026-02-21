from __future__ import annotations

from app.models.organization import Organization


def _login(client, email: str, password: str) -> tuple[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    payload = response.json()["data"]
    return payload["access_token"], payload["user"]["tenant_id"]


def _create_campaign(client, token: str, name: str, domain: str) -> dict:
    response = client.post(
        "/api/v1/campaigns",
        json={"name": name, "domain": domain},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    return response.json()["data"]


def _set_org_plan(db_session, org_id: str, plan_type: str) -> None:  # noqa: ANN001
    org = db_session.query(Organization).filter(Organization.id == org_id).first()
    assert org is not None
    org.plan_type = plan_type
    db_session.commit()


def test_campaign_strategy_org_isolation_enforced(client, db_session) -> None:
    token_a, tenant_a = _login(client, "org-admin@example.com", "pass-org-admin")
    _set_org_plan(db_session, tenant_a, "enterprise")

    token_b, _tenant_b = _login(client, "b@example.com", "pass-b")
    campaign_b = _create_campaign(client, token_b, "Strategy B", "strategy-b.example")

    response = client.get(
        f"/api/v1/campaigns/{campaign_b['id']}/strategy",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert response.status_code == 404


def test_campaign_strategy_feature_gate_enforced(client, db_session) -> None:
    token, tenant_id = _login(client, "org-admin@example.com", "pass-org-admin")
    _set_org_plan(db_session, tenant_id, "standard")
    campaign = _create_campaign(client, token, "Strategy Gate", "strategy-gate.example")

    response = client.get(
        f"/api/v1/campaigns/{campaign['id']}/strategy",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
    assert response.json()["errors"][0]["details"]["reason_code"] == "feature_not_available"


def test_campaign_strategy_enterprise_enables_competitor_diagnostics(client, db_session) -> None:
    token, tenant_id = _login(client, "org-admin@example.com", "pass-org-admin")
    _set_org_plan(db_session, tenant_id, "enterprise")
    campaign = _create_campaign(client, token, "Strategy Ent", "strategy-ent.example")

    response = client.get(
        f"/api/v1/campaigns/{campaign['id']}/strategy",
        params={"date_from": "2026-02-01T00:00:00Z", "date_to": "2026-02-20T00:00:00Z"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert "competitor_data_unavailable" in data["detected_scenarios"]


def test_campaign_strategy_non_enterprise_suppresses_competitor_module(client, db_session) -> None:
    token, tenant_id = _login(client, "org-admin@example.com", "pass-org-admin")
    _set_org_plan(db_session, tenant_id, "internal_anchor")
    campaign = _create_campaign(client, token, "Strategy Pro", "strategy-pro.example")

    response = client.get(
        f"/api/v1/campaigns/{campaign['id']}/strategy",
        params={"date_from": "2026-02-01T00:00:00Z", "date_to": "2026-02-20T00:00:00Z"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert "competitor_data_unavailable" not in data["detected_scenarios"]
    assert data["meta"]["tier"] == "pro"


def test_campaign_strategy_deterministic_output_for_fixed_window(client, db_session) -> None:
    token, tenant_id = _login(client, "org-admin@example.com", "pass-org-admin")
    _set_org_plan(db_session, tenant_id, "enterprise")
    campaign = _create_campaign(client, token, "Strategy Deterministic", "strategy-deterministic.example")

    params = {"date_from": "2026-02-01T00:00:00Z", "date_to": "2026-02-20T00:00:00Z"}
    response_a = client.get(
        f"/api/v1/campaigns/{campaign['id']}/strategy",
        params=params,
        headers={"Authorization": f"Bearer {token}"},
    )
    response_b = client.get(
        f"/api/v1/campaigns/{campaign['id']}/strategy",
        params=params,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response_a.status_code == 200
    assert response_b.status_code == 200
    assert response_a.json()["data"] == response_b.json()["data"]

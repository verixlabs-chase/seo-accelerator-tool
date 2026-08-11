from __future__ import annotations

from app.models.product_analytics import ProductAnalyticsEvent


def _login(client, email: str, password: str) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


def _create_campaign(client, token: str) -> dict:
    response = client.post(
        "/api/v1/campaigns",
        json={"name": "Outcome API Campaign", "domain": "outcome-api.example"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    return response.json()["data"]


def test_measure_and_list_recommendation_outcomes(client, db_session) -> None:
    token = _login(client, "a@example.com", "pass-a")
    headers = {"Authorization": f"Bearer {token}"}
    campaign = _create_campaign(client, token)

    recommendations = client.get(
        f"/api/v1/intelligence/recommendations?campaign_id={campaign['id']}",
        headers=headers,
    )
    assert recommendations.status_code == 200
    recommendation = recommendations.json()["data"]["items"][0]

    for target_state in ("VALIDATED", "APPROVED"):
        transition = client.post(
            (
                f"/api/v1/intelligence/recommendations/{recommendation['id']}/transition"
                f"?campaign_id={campaign['id']}"
            ),
            json={"target_state": target_state},
            headers=headers,
        )
        assert transition.status_code == 200

    measured = client.post(
        (
            f"/api/v1/intelligence/recommendations/{recommendation['id']}/measure-outcome"
            f"?campaign_id={campaign['id']}"
        ),
        headers=headers,
    )
    assert measured.status_code == 200
    measured_payload = measured.json()["data"]
    assert measured_payload["created"] is True
    assert measured_payload["outcome"]["measurement_kind"] == "opportunity_score"
    assert measured_payload["outcome"]["causal_proof"] is False
    assert measured_payload["learning"] == {
        "state": "observation_only",
        "observations_recorded": 1,
        "policy_updates_enabled": False,
        "causal_claims_allowed": False,
        "minimum_outcomes_before_review": 5,
    }
    measured_event = (
        db_session.query(ProductAnalyticsEvent)
        .filter(
            ProductAnalyticsEvent.campaign_id == campaign["id"],
            ProductAnalyticsEvent.event_name == "action.outcome_available",
        )
        .one()
    )
    assert measured_event.source == "product_server"
    assert measured_event.properties_json == {"result_direction": "unchanged"}

    duplicate = client.post(
        (
            f"/api/v1/intelligence/recommendations/{recommendation['id']}/measure-outcome"
            f"?campaign_id={campaign['id']}"
        ),
        headers=headers,
    )
    assert duplicate.status_code == 200
    assert duplicate.json()["data"]["created"] is False

    history = client.get(
        f"/api/v1/intelligence/outcomes?campaign_id={campaign['id']}",
        headers=headers,
    )
    assert history.status_code == 200
    history_payload = history.json()["data"]
    assert history_payload["count"] == 1
    assert history_payload["summary"]["unchanged_count"] == 1
    assert history_payload["truth"]["classification"] == "heuristic"
    assert "causal_claims_are_disabled" in history_payload["truth"]["reasons"]


def test_outcome_endpoints_are_tenant_scoped(client) -> None:
    token_a = _login(client, "a@example.com", "pass-a")
    token_b = _login(client, "b@example.com", "pass-b")
    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}
    campaign = _create_campaign(client, token_a)
    recommendations = client.get(
        f"/api/v1/intelligence/recommendations?campaign_id={campaign['id']}",
        headers=headers_a,
    )
    recommendation = recommendations.json()["data"]["items"][0]

    history = client.get(
        f"/api/v1/intelligence/outcomes?campaign_id={campaign['id']}",
        headers=headers_b,
    )
    assert history.status_code == 404

    measurement = client.post(
        (
            f"/api/v1/intelligence/recommendations/{recommendation['id']}/measure-outcome"
            f"?campaign_id={campaign['id']}"
        ),
        headers=headers_b,
    )
    assert measurement.status_code == 404

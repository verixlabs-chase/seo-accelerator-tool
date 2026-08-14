from __future__ import annotations

import json

from app.models.intelligence import StrategyRecommendation
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
        json={"name": "Checklist API Campaign", "domain": "checklist-api.example"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    return response.json()["data"]


def test_checklist_api_persists_progress_and_blocks_cross_tenant_updates(
    client,
    db_session,
) -> None:
    token_a = _login(client, "a@example.com", "pass-a")
    token_b = _login(client, "b@example.com", "pass-b")
    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}
    campaign = _create_campaign(client, token_a)
    recommendation = StrategyRecommendation(
        tenant_id=campaign["tenant_id"],
        campaign_id=campaign["id"],
        recommendation_type=(
            "policy::core_web_vitals_failure::technical.reduce_render_blocking"
        ),
        rationale="The main content is loading too slowly.",
        confidence=0.91,
        confidence_score=0.91,
        evidence_json=json.dumps({"evidence": ["LCP is above the poor boundary"]}),
        risk_tier=3,
        rollback_plan_json=json.dumps({"steps": ["restore prior asset loading"]}),
        status="GENERATED",
    )
    db_session.add(recommendation)
    db_session.commit()

    listed = client.get(
        f"/api/v1/intelligence/recommendations?campaign_id={campaign['id']}",
        headers=headers_a,
    )
    assert listed.status_code == 200
    item = next(
        row
        for row in listed.json()["data"]["items"]
        if row["id"] == recommendation.id
    )
    work_item = item["action_plan"]["work_item"]
    assert work_item["cadence"] == "daily"
    assert work_item["progress"]["required_total"] == 3
    first_value_event = (
        db_session.query(ProductAnalyticsEvent)
        .filter(
            ProductAnalyticsEvent.campaign_id == campaign["id"],
            ProductAnalyticsEvent.event_name == "value.first_verified_insight",
        )
        .one()
    )
    assert first_value_event.source == "product_server"

    first_step = work_item["steps"][0]
    updated = client.patch(
        (
            f"/api/v1/intelligence/action-plans/{work_item['id']}"
            f"/steps/{first_step['id']}?campaign_id={campaign['id']}"
        ),
        json={"status": "done"},
        headers=headers_a,
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["work_item"]["progress"]["completed_required"] == 1
    measurement = updated.json()["data"]["work_item"]["measurement"]
    assert measurement["measurement_status"] == "insufficient_baseline"
    assert measurement["readiness"] == "baseline_unavailable"
    forecast = updated.json()["data"]["work_item"]["forecast"]
    assert forecast["forecast_status"] == "not_available"
    assert forecast["data_quality"] == "insufficient"
    assert "scope_not_defined" in {
        reason["code"] for reason in forecast["unavailable_reasons"]
    }

    learning = client.get(
        f"/api/v1/intelligence/outcome-learning?campaign_id={campaign['id']}",
        headers=headers_a,
    )
    assert learning.status_code == 200
    learning_payload = learning.json()["data"]
    assert learning_payload["summary"]["measured_actions"] == 0
    assert learning_payload["learning"]["state"] == "review_only"
    assert learning_payload["learning"]["automatic_policy_updates_enabled"] is False
    assert learning_payload["truth"]["classification"] == "unavailable"
    review_too_early = client.put(
        (
            f"/api/v1/intelligence/outcome-learning/{measurement['id']}"
            f"/review?campaign_id={campaign['id']}"
        ),
        json={"decision": "included", "confounder_codes": [], "note": None},
        headers=headers_a,
    )
    assert review_too_early.status_code == 409
    completed_event = (
        db_session.query(ProductAnalyticsEvent)
        .filter(
            ProductAnalyticsEvent.campaign_id == campaign["id"],
            ProductAnalyticsEvent.event_name == "action.step_completed",
        )
        .one()
    )
    assert completed_event.source == "product_server"

    generated_forecast = client.post(
        (
            f"/api/v1/intelligence/action-plans/{work_item['id']}"
            f"/forecast?campaign_id={campaign['id']}"
        ),
        headers=headers_a,
    )
    assert generated_forecast.status_code == 200
    assert generated_forecast.json()["data"]["forecast"]["id"] == forecast["id"]

    too_early = client.post(
        (
            f"/api/v1/intelligence/action-plans/{work_item['id']}"
            f"/measure?campaign_id={campaign['id']}"
        ),
        headers=headers_a,
    )
    assert too_early.status_code == 409

    refreshed = client.get(
        f"/api/v1/intelligence/recommendations?campaign_id={campaign['id']}",
        headers=headers_a,
    )
    refreshed_item = next(
        row
        for row in refreshed.json()["data"]["items"]
        if row["id"] == recommendation.id
    )
    assert (
        refreshed_item["action_plan"]["work_item"]["steps"][0]["status"]
        == "done"
    )

    blocked = client.patch(
        (
            f"/api/v1/intelligence/action-plans/{work_item['id']}"
            f"/steps/{first_step['id']}?campaign_id={campaign['id']}"
        ),
        json={"status": "not_started"},
        headers=headers_b,
    )
    assert blocked.status_code == 404

    blocked_measurement = client.post(
        (
            f"/api/v1/intelligence/action-plans/{work_item['id']}"
            f"/measure?campaign_id={campaign['id']}"
        ),
        headers=headers_b,
    )
    assert blocked_measurement.status_code == 404

    blocked_forecast = client.post(
        (
            f"/api/v1/intelligence/action-plans/{work_item['id']}"
            f"/forecast?campaign_id={campaign['id']}"
        ),
        headers=headers_b,
    )
    assert blocked_forecast.status_code == 404

    blocked_learning = client.get(
        f"/api/v1/intelligence/outcome-learning?campaign_id={campaign['id']}",
        headers=headers_b,
    )
    assert blocked_learning.status_code == 404

    blocked_review = client.put(
        (
            f"/api/v1/intelligence/outcome-learning/{measurement['id']}"
            f"/review?campaign_id={campaign['id']}"
        ),
        json={"decision": "excluded", "confounder_codes": [], "note": None},
        headers=headers_b,
    )
    assert blocked_review.status_code == 404

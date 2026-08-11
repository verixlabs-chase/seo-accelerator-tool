from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

from app.models.campaign import Campaign
from app.models.organization import Organization
from app.models.product_analytics import ProductAnalyticsEvent, ProductFeedback
from app.models.user import User
from app.services import product_analytics_service


def _login(client, email: str, password: str) -> tuple[str, dict]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    payload = response.json()["data"]
    return payload["access_token"], payload["user"]


def _campaign_for_org(db_session, *, organization_id: str, tenant_id: str) -> Campaign:
    row = Campaign(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        organization_id=organization_id,
        name="Value Measurement Location",
        domain="value-measurement.example",
        setup_state="Active",
    )
    db_session.add(row)
    db_session.commit()
    return row


def test_governed_events_are_scoped_validated_and_idempotent(client, db_session) -> None:
    token, principal = _login(client, "org-admin@example.com", "pass-org-admin")
    user = db_session.query(User).filter(User.email == "org-admin@example.com").one()
    campaign = _campaign_for_org(
        db_session,
        organization_id=principal["organization_id"],
        tenant_id=user.tenant_id,
    )
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "event_name": "onboarding.completed",
        "campaign_id": campaign.id,
        "properties": {"result_status": "success"},
        "idempotency_key": f"onboarding.completed:{campaign.id}",
    }

    created = client.post("/api/v1/product-analytics/events", json=payload, headers=headers)
    replay = client.post("/api/v1/product-analytics/events", json=payload, headers=headers)

    assert created.status_code == 200
    assert created.json()["data"]["created"] is True
    assert replay.status_code == 200
    assert replay.json()["data"]["created"] is False
    assert db_session.query(ProductAnalyticsEvent).count() == 1
    saved = db_session.query(ProductAnalyticsEvent).one()
    assert saved.organization_id == principal["organization_id"]
    assert saved.campaign_id == campaign.id
    assert saved.properties_json == {"result_status": "success"}

    prohibited = client.post(
        "/api/v1/product-analytics/events",
        json={
            "event_name": "onboarding.started",
            "properties": {"entry_point": "workspace_setup", "email": "owner@example.com"},
        },
        headers=headers,
    )
    assert prohibited.status_code == 400
    assert (
        prohibited.json()["errors"][0]["details"]["reason_code"]
        == "prohibited_analytics_field"
    )

    other_org_campaign = Campaign(
        id=str(uuid.uuid4()),
        tenant_id=(db_session.query(User).filter(User.email == "b@example.com").one().tenant_id),
        organization_id=(db_session.query(User).filter(User.email == "b@example.com").one().tenant_id),
        name="Other Organization",
        domain="other.example",
        setup_state="Active",
    )
    db_session.add(other_org_campaign)
    db_session.commit()
    wrong_scope = client.post(
        "/api/v1/product-analytics/events",
        json={
            "event_name": "recommendation.viewed",
            "campaign_id": other_org_campaign.id,
            "properties": {"surface": "next_steps"},
        },
        headers=headers,
    )
    assert wrong_scope.status_code == 403
    assert (
        wrong_scope.json()["errors"][0]["details"]["reason_code"]
        == "organization_scope_mismatch"
    )

    server_only = client.post(
        "/api/v1/product-analytics/events",
        json={
            "event_name": "action.step_completed",
            "campaign_id": campaign.id,
            "properties": {"surface": "next_steps"},
        },
        headers=headers,
    )
    assert server_only.status_code == 400
    assert (
        server_only.json()["errors"][0]["details"]["reason_code"]
        == "event_requires_server_evidence"
    )


def test_structured_feedback_has_no_free_form_content(client, db_session) -> None:
    token, principal = _login(client, "org-admin@example.com", "pass-org-admin")
    user = db_session.query(User).filter(User.email == "org-admin@example.com").one()
    campaign = _campaign_for_org(
        db_session,
        organization_id=principal["organization_id"],
        tenant_id=user.tenant_id,
    )
    response = client.post(
        "/api/v1/product-analytics/feedback",
        json={
            "context": "forecast_trust",
            "subject_type": "forecast",
            "subject_id": str(uuid.uuid4()),
            "campaign_id": campaign.id,
            "rating": 5,
            "reason_code": "believable",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["feedback"]["saved"] is True
    saved = db_session.query(ProductFeedback).one()
    assert saved.context == "forecast_trust"
    assert saved.rating == 5

    free_form = client.post(
        "/api/v1/product-analytics/feedback",
        json={
            "context": "forecast_trust",
            "subject_type": "forecast",
            "campaign_id": campaign.id,
            "rating": 1,
            "reason_code": "not_believable",
            "note": "This contains business details that must not be accepted.",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert free_form.status_code == 422


def test_platform_value_summary_is_aggregate_and_excludes_synthetic_events(client, db_session) -> None:
    token, principal = _login(client, "org-admin@example.com", "pass-org-admin")
    user = db_session.query(User).filter(User.email == "org-admin@example.com").one()
    organization_id = principal["organization_id"]
    organization = db_session.query(Organization).filter(Organization.id == organization_id).one()
    organization.plan_type = "solo"
    campaign = _campaign_for_org(
        db_session,
        organization_id=organization_id,
        tenant_id=user.tenant_id,
    )
    headers = {"Authorization": f"Bearer {token}"}
    now = datetime.now(UTC)
    client_events = [
        (
            "onboarding.started",
            {"entry_point": "workspace_setup"},
            now - timedelta(hours=3),
        ),
        (
            "onboarding.completed",
            {"result_status": "success"},
            now - timedelta(hours=2),
        ),
    ]
    for index, (event_name, properties, occurred_at) in enumerate(client_events):
        response = client.post(
            "/api/v1/product-analytics/events",
            json={
                "event_name": event_name,
                "campaign_id": campaign.id,
                "properties": properties,
                "occurred_at": occurred_at.isoformat(),
                "idempotency_key": f"value-summary:{index}",
            },
            headers=headers,
        )
        assert response.status_code == 200

    product_analytics_service.record_event(
        db_session,
        tenant_id=user.tenant_id,
        organization_id=organization_id,
        actor_user_id=user.id,
        event_name="value.first_verified_insight",
        campaign_id=campaign.id,
        properties={"value_kind": "recommendation_with_evidence"},
        occurred_at=now - timedelta(hours=1),
        idempotency_key="value-summary:server:first-value",
        source="product_server",
    )
    product_analytics_service.record_event(
        db_session,
        tenant_id=user.tenant_id,
        organization_id=organization_id,
        actor_user_id=user.id,
        event_name="action.step_completed",
        campaign_id=campaign.id,
        properties={"surface": "next_steps"},
        occurred_at=now,
        idempotency_key="value-summary:server:step-completed",
        source="product_server",
    )

    db_session.add(
        ProductAnalyticsEvent(
            tenant_id=user.tenant_id,
            organization_id=organization_id,
            actor_user_id=user.id,
            campaign_id=campaign.id,
            event_name="action.step_completed",
            category="actions",
            schema_version="1.0",
            plan_type="solo",
            source="test_fixture",
            properties_json={"surface": "next_steps"},
            is_synthetic=True,
            occurred_at=now,
            received_at=now,
        )
    )
    db_session.add(
        ProductFeedback(
            tenant_id=user.tenant_id,
            organization_id=organization_id,
            actor_user_id=user.id,
            campaign_id=campaign.id,
            context="forecast_trust",
            subject_type="forecast",
            subject_id=str(uuid.uuid4()),
            rating=1,
            reason_code="not_believable",
            plan_type="solo",
            is_synthetic=True,
            created_at=now,
        )
    )
    db_session.commit()

    platform_token, _ = _login(client, "platform-admin@example.com", "pass-platform-admin")
    summary_response = client.get(
        "/api/v1/platform/product-value/summary?days=30",
        headers={"Authorization": f"Bearer {platform_token}"},
    )
    assert summary_response.status_code == 200
    summary = summary_response.json()["data"]
    assert summary["funnel"]["activated"] == 1
    assert summary["funnel"]["first_value"] == 1
    assert summary["funnel"]["action_completed"] == 1
    assert summary["funnel"]["average_hours_to_first_value"] == 2.0
    assert summary["privacy"]["synthetic_events_excluded"] == 1
    assert summary["privacy"]["synthetic_feedback_excluded"] == 1
    assert summary["feedback"] == []
    assert any(item["plan_type"] == "solo" for item in summary["cohorts"])
    assert organization_id not in json.dumps(summary)

    taxonomy_response = client.get(
        "/api/v1/platform/product-value/taxonomy",
        headers={"Authorization": f"Bearer {platform_token}"},
    )
    assert taxonomy_response.status_code == 200
    taxonomy = taxonomy_response.json()["data"]
    assert taxonomy["autocapture_enabled"] is False
    assert taxonomy["session_replay_enabled"] is False
    assert all(item["owner"] for item in taxonomy["events"])
    assert all(item["purpose"] for item in taxonomy["events"])
    assert all(item["retention_days"] > 0 for item in taxonomy["events"])

    denied = client.get(
        "/api/v1/platform/product-value/summary",
        headers=headers,
    )
    assert denied.status_code == 403

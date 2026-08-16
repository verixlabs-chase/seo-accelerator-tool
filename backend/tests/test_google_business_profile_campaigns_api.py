from __future__ import annotations

from app.models.audit_log import AuditLog
from app.models.campaign import Campaign
from app.models.data_connection import DataConnection
from app.models.fleet_job import FleetJob
from app.models.google_business_profile_campaign import (
    GoogleBusinessProfileCampaign,
    GoogleBusinessProfileCampaignVariant,
)
from app.models.portfolio import Portfolio
from app.services.commercial_plan_service import apply_commercial_plan


def _login(client, email: str, password: str) -> tuple[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    data = response.json()["data"]
    return data["access_token"], data["user"]["organization_id"]


def _create_location(client, *, token: str, organization_id: str, name: str, city: str) -> dict:
    response = client.post(
        f"/api/v1/organizations/{organization_id}/business-locations",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": name,
            "domain": f"{name.lower().replace(' ', '-')}.example.com",
            "city": city,
            "region": "Texas",
        },
    )
    assert response.status_code == 200
    return response.json()["data"]["business_location"]


def _add_campaign_and_connection(
    db_session,
    *,
    organization_id: str,
    location: dict,
    mutation_enabled: bool,
) -> Campaign:
    portfolio = (
        db_session.query(Portfolio)
        .filter(
            Portfolio.organization_id == organization_id,
            Portfolio.business_location_id == location["id"],
        )
        .one()
    )
    campaign = Campaign(
        tenant_id=organization_id,
        organization_id=organization_id,
        business_location_id=location["id"],
        portfolio_id=portfolio.id,
        name=f"{location['name']} SEO",
        domain=location["domain"],
        setup_state="Active",
    )
    db_session.add(campaign)
    db_session.flush()
    db_session.add(
        DataConnection(
            tenant_id=organization_id,
            organization_id=organization_id,
            business_location_id=location["id"],
            campaign_id=campaign.id,
            provider_name="google_business_profile",
            external_resource_id=f"locations/{location['id'].replace('-', '')[:20]}",
            external_resource_name=location["name"],
            resource_scope="owned_business_profile",
            status="connected",
            connection_metadata={
                "profile_verified": True,
                "permission_verified": True,
                "mutation_enabled": mutation_enabled,
            },
        )
    )
    db_session.commit()
    return campaign


def test_profile_campaign_freezes_per_location_preview_and_approval_hold(
    client,
    db_session,
) -> None:
    token, organization_id = _login(client, "org-admin@example.com", "pass-org-admin")
    apply_commercial_plan(
        db_session,
        organization_id=organization_id,
        plan_code="multi_location",
    )
    db_session.commit()
    headers = {"Authorization": f"Bearer {token}"}

    north = _create_location(
        client,
        token=token,
        organization_id=organization_id,
        name="Dallas North",
        city="Dallas",
    )
    south = _create_location(
        client,
        token=token,
        organization_id=organization_id,
        name="Fort Worth South",
        city="Fort Worth",
    )
    _add_campaign_and_connection(
        db_session,
        organization_id=organization_id,
        location=north,
        mutation_enabled=True,
    )
    _add_campaign_and_connection(
        db_session,
        organization_id=organization_id,
        location=south,
        mutation_enabled=False,
    )

    group_response = client.post(
        f"/api/v1/organizations/{organization_id}/location-groups",
        headers=headers,
        json={"name": "DFW profiles", "location_ids": [north["id"], south["id"]]},
    )
    assert group_response.status_code == 201
    group = group_response.json()["data"]["location_group"]
    snapshot_response = client.post(
        f"/api/v1/organizations/{organization_id}/target-snapshots",
        headers=headers,
        json={
            "action_key": "gbp_local_post",
            "request_key": "gbp-post-target-1",
            "location_group_id": group["id"],
        },
    )
    assert snapshot_response.status_code == 201
    snapshot = snapshot_response.json()["data"]["target_snapshot"]

    create_payload = {
        "target_snapshot_id": snapshot["id"],
        "request_key": "gbp-post-campaign-1",
        "name": "Summer service reminder",
        "action_type": "local_post",
        "payload_template": {
            "post_type": "update",
            "summary": "Book local service from {location_name} in {city}.",
            "call_to_action": "learn_more",
            "destination_url": "{website}/book",
        },
    }
    create_response = client.post(
        f"/api/v1/organizations/{organization_id}/profile-campaigns",
        headers=headers,
        json=create_payload,
    )
    assert create_response.status_code == 201
    draft = create_response.json()["data"]["profile_campaign"]
    assert draft["status"] == "draft"
    assert draft["provider_changes_enabled"] is False

    replay_response = client.post(
        f"/api/v1/organizations/{organization_id}/profile-campaigns",
        headers=headers,
        json=create_payload,
    )
    assert replay_response.status_code == 201
    assert replay_response.json()["data"]["created"] is False
    assert replay_response.json()["meta"]["idempotent_replay"] is True

    apply_commercial_plan(
        db_session,
        organization_id=organization_id,
        plan_code="solo",
    )
    gated_preflight = client.post(
        f"/api/v1/organizations/{organization_id}/profile-campaigns/{draft['id']}/preflight",
        headers=headers,
        json={"expected_version": draft["version"]},
    )
    assert gated_preflight.status_code == 403
    assert gated_preflight.json()["errors"][0]["details"]["reason_code"] == (
        "profile_campaign_upgrade_required"
    )
    assert db_session.query(GoogleBusinessProfileCampaignVariant).count() == 0
    apply_commercial_plan(
        db_session,
        organization_id=organization_id,
        plan_code="multi_location",
    )
    preflight_response = client.post(
        f"/api/v1/organizations/{organization_id}/profile-campaigns/{draft['id']}/preflight",
        headers=headers,
        json={"expected_version": draft["version"]},
    )
    assert preflight_response.status_code == 200
    checked = preflight_response.json()["data"]["profile_campaign"]
    assert checked["status"] == "awaiting_approval"
    assert checked["counts"] == {"targeted": 2, "ready": 1, "blocked": 1}
    assert checked["preflight"]["provider_changes_enabled"] is False
    assert len(checked["approval_hash"]) == 64
    variants = {item["location_name"]: item for item in checked["variants"]}
    assert variants["Dallas North"]["status"] == "ready"
    assert variants["Dallas North"]["rendered_payload"]["summary"] == (
        "Book local service from Dallas North in Dallas."
    )
    assert variants["Dallas North"]["rendered_payload"]["destination_url"].endswith(
        ".example.com/book"
    )
    assert variants["Fort Worth South"]["reason_code"] == "single_profile_action_validated"
    assert "validated" in variants["Fort Worth South"]["message"]

    apply_commercial_plan(
        db_session,
        organization_id=organization_id,
        plan_code="solo",
    )
    gated_approval = client.post(
        f"/api/v1/organizations/{organization_id}/profile-campaigns/{draft['id']}/approve",
        headers=headers,
        json={"expected_version": checked["version"]},
    )
    assert gated_approval.status_code == 403
    assert gated_approval.json()["errors"][0]["details"]["reason_code"] == (
        "profile_campaign_upgrade_required"
    )
    apply_commercial_plan(
        db_session,
        organization_id=organization_id,
        plan_code="multi_location",
    )
    approval_response = client.post(
        f"/api/v1/organizations/{organization_id}/profile-campaigns/{draft['id']}/approve",
        headers=headers,
        json={"expected_version": checked["version"]},
    )
    assert approval_response.status_code == 200
    approved = approval_response.json()["data"]["profile_campaign"]
    assert approved["status"] == "approved_hold"
    assert approved["approval"]["approved"] is True
    assert approved["provider_changes_enabled"] is False
    assert db_session.query(FleetJob).count() == 0
    assert db_session.query(GoogleBusinessProfileCampaign).count() == 1
    assert db_session.query(GoogleBusinessProfileCampaignVariant).count() == 2

    events = {
        row.event_type
        for row in db_session.query(AuditLog)
        .filter(AuditLog.tenant_id == organization_id)
        .all()
    }
    assert "google_business_profile.profile_campaign.created" in events
    assert "google_business_profile.profile_campaign.preflight_completed" in events
    assert "google_business_profile.profile_campaign.approved_for_hold" in events


def test_profile_campaign_rejects_solo_cross_org_and_unconfirmed_content(
    client,
    db_session,
) -> None:
    token_a, organization_a = _login(client, "org-admin@example.com", "pass-org-admin")
    token_b, organization_b = _login(client, "b@example.com", "pass-b")
    location = _create_location(
        client,
        token=token_a,
        organization_id=organization_a,
        name="Scoped profile",
        city="Austin",
    )
    _add_campaign_and_connection(
        db_session,
        organization_id=organization_a,
        location=location,
        mutation_enabled=True,
    )
    snapshot_response = client.post(
        f"/api/v1/organizations/{organization_a}/target-snapshots",
        headers={"Authorization": f"Bearer {token_a}"},
        json={
            "action_key": "gbp_local_post",
            "request_key": "scoped-gbp-target",
            "included_location_ids": [location["id"]],
        },
    )
    snapshot = snapshot_response.json()["data"]["target_snapshot"]
    payload = {
        "target_snapshot_id": snapshot["id"],
        "request_key": "scoped-gbp-campaign",
        "name": "Scoped post",
        "action_type": "local_post",
        "payload_template": {"summary": "Serving {city}.", "call_to_action": "none"},
    }

    cross_org = client.post(
        f"/api/v1/organizations/{organization_a}/profile-campaigns",
        headers={"Authorization": f"Bearer {token_b}"},
        json=payload,
    )
    assert cross_org.status_code == 403

    hidden = client.post(
        f"/api/v1/organizations/{organization_b}/profile-campaigns",
        headers={"Authorization": f"Bearer {token_b}"},
        json=payload,
    )
    assert hidden.status_code == 403
    assert hidden.json()["errors"][0]["details"]["reason_code"] == (
        "profile_campaign_upgrade_required"
    )

    apply_commercial_plan(
        db_session,
        organization_id=organization_a,
        plan_code="multi_location",
    )
    db_session.commit()
    invalid = client.post(
        f"/api/v1/organizations/{organization_a}/profile-campaigns",
        headers={"Authorization": f"Bearer {token_a}"},
        json={
            **payload,
            "request_key": "invalid-gbp-placeholder",
            "payload_template": {
                "summary": "Call {invented_phone_number} today.",
                "call_to_action": "none",
            },
        },
    )
    assert invalid.status_code == 422
    assert invalid.json()["errors"][0]["details"]["reason_code"] == (
        "profile_campaign_unknown_placeholder"
    )

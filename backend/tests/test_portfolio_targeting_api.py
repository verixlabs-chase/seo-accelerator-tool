from __future__ import annotations

import json

from app.models.audit_log import AuditLog
from app.models.campaign import Campaign
from app.models.portfolio_targeting import PortfolioTargetSnapshot
from app.services.commercial_plan_service import apply_commercial_plan


def _login(client, email: str, password: str) -> tuple[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    return data["access_token"], data["user"]["organization_id"]


def _create_location(
    client,
    *,
    token: str,
    organization_id: str,
    name: str,
    city: str,
    region: str = "Texas",
) -> dict:
    response = client.post(
        f"/api/v1/organizations/{organization_id}/business-locations",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": name,
            "domain": f"{name.lower().replace(' ', '-')}.example.com",
            "city": city,
            "region": region,
        },
    )
    assert response.status_code == 200
    return response.json()["data"]["business_location"]


def test_saved_groups_and_immutable_target_previews_are_scoped_and_idempotent(
    client,
    db_session,
) -> None:
    token, org_id = _login(client, "org-admin@example.com", "pass-org-admin")
    apply_commercial_plan(
        db_session,
        organization_id=org_id,
        plan_code="multi_location",
    )
    headers = {"Authorization": f"Bearer {token}"}
    dallas = _create_location(
        client,
        token=token,
        organization_id=org_id,
        name="Dallas North",
        city="Dallas",
    )
    austin = _create_location(
        client,
        token=token,
        organization_id=org_id,
        name="Austin Central",
        city="Austin",
    )
    houston = _create_location(
        client,
        token=token,
        organization_id=org_id,
        name="Houston West",
        city="Houston",
    )
    campaigns = [
        Campaign(
            tenant_id=org_id,
            organization_id=org_id,
            business_location_id=location["id"],
            name=f"{location['name']} SEO",
            domain=location["domain"],
            setup_state="Active",
        )
        for location in (dallas, austin)
    ]
    db_session.add_all(campaigns)
    db_session.commit()

    create_response = client.post(
        f"/api/v1/organizations/{org_id}/location-groups",
        headers=headers,
        json={
            "name": "Texas team",
            "description": "Locations managed by the Texas team.",
            "location_ids": [dallas["id"], austin["id"], houston["id"]],
        },
    )
    assert create_response.status_code == 201
    group = create_response.json()["data"]["location_group"]
    assert group["version"] == 1
    assert group["member_count"] == 3
    assert [member["name"] for member in group["members"]] == [
        "Austin Central",
        "Dallas North",
        "Houston West",
    ]

    update_response = client.patch(
        f"/api/v1/organizations/{org_id}/location-groups/{group['id']}",
        headers=headers,
        json={
            "expected_version": 1,
            "name": "Texas service team",
            "description": "Locations managed together.",
            "status": "active",
            "location_ids": [dallas["id"], austin["id"], houston["id"]],
        },
    )
    assert update_response.status_code == 200
    updated_group = update_response.json()["data"]["location_group"]
    assert updated_group["version"] == 2

    stale_response = client.patch(
        f"/api/v1/organizations/{org_id}/location-groups/{group['id']}",
        headers=headers,
        json={
            "expected_version": 1,
            "name": "Stale edit",
            "status": "active",
            "location_ids": [dallas["id"]],
        },
    )
    assert stale_response.status_code == 409
    assert (
        stale_response.json()["errors"][0]["details"]["reason_code"]
        == "location_group_version_conflict"
    )

    snapshot_payload = {
        "action_key": "portfolio_review",
        "request_key": "test-target-preview-1",
        "location_group_id": group["id"],
        "select_all_active": False,
        "regions": [],
        "included_location_ids": [],
        "excluded_location_ids": [austin["id"]],
    }
    snapshot_response = client.post(
        f"/api/v1/organizations/{org_id}/target-snapshots",
        headers=headers,
        json=snapshot_payload,
    )
    assert snapshot_response.status_code == 201
    snapshot_data = snapshot_response.json()["data"]
    snapshot = snapshot_data["target_snapshot"]
    assert snapshot_data["created"] is True
    assert snapshot["immutable"] is True
    assert snapshot["location_group_version"] == 2
    assert snapshot["target_count"] == 1
    assert snapshot["blocked_count"] == 1
    assert len(snapshot["target_hash"]) == 64
    assert snapshot["targets"][0]["location_id"] == dallas["id"]
    exceptions = {item["location_id"]: item for item in snapshot["exceptions"]}
    assert exceptions[austin["id"]]["reason"] == "explicitly_excluded"
    assert exceptions[austin["id"]]["blocked"] is False
    assert exceptions[houston["id"]]["reason"] == "campaign_missing"
    assert exceptions[houston["id"]]["blocked"] is True

    replay_response = client.post(
        f"/api/v1/organizations/{org_id}/target-snapshots",
        headers=headers,
        json=snapshot_payload,
    )
    assert replay_response.status_code == 201
    replay_data = replay_response.json()
    assert replay_data["data"]["created"] is False
    assert replay_data["data"]["target_snapshot"]["id"] == snapshot["id"]
    assert replay_data["meta"]["idempotent_replay"] is True

    conflict_response = client.post(
        f"/api/v1/organizations/{org_id}/target-snapshots",
        headers=headers,
        json={**snapshot_payload, "excluded_location_ids": []},
    )
    assert conflict_response.status_code == 409
    assert (
        conflict_response.json()["errors"][0]["details"]["reason_code"]
        == "target_request_key_conflict"
    )

    list_response = client.get(
        f"/api/v1/organizations/{org_id}/target-snapshots",
        headers=headers,
    )
    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()["data"]["items"]] == [
        snapshot["id"]
    ]

    immutable_route_response = client.patch(
        f"/api/v1/organizations/{org_id}/target-snapshots/{snapshot['id']}",
        headers=headers,
        json={"target_count": 99},
    )
    assert immutable_route_response.status_code == 404

    persisted = db_session.get(PortfolioTargetSnapshot, snapshot["id"])
    assert persisted is not None
    assert persisted.target_hash == snapshot["target_hash"]
    audit = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.tenant_id == org_id,
            AuditLog.event_type == "portfolio.target_snapshot.created",
        )
        .one()
    )
    audit_payload = json.loads(audit.payload_json)
    assert audit_payload["target_snapshot_id"] == snapshot["id"]
    assert audit_payload["target_count"] == 1


def test_targeting_rejects_cross_organization_locations_and_requests(client) -> None:
    token_a, org_a = _login(client, "org-admin@example.com", "pass-org-admin")
    token_b, org_b = _login(client, "b@example.com", "pass-b")
    location_b = _create_location(
        client,
        token=token_b,
        organization_id=org_b,
        name="Other account location",
        city="Tulsa",
        region="Oklahoma",
    )

    cross_location_response = client.post(
        f"/api/v1/organizations/{org_a}/location-groups",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"name": "Wrong account", "location_ids": [location_b["id"]]},
    )
    assert cross_location_response.status_code == 403
    assert (
        cross_location_response.json()["errors"][0]["details"]["reason_code"]
        == "one_or_more_locations_unavailable"
    )

    cross_request_response = client.get(
        f"/api/v1/organizations/{org_a}/location-groups",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert cross_request_response.status_code == 403

    empty_selection_response = client.post(
        f"/api/v1/organizations/{org_a}/target-snapshots",
        headers={"Authorization": f"Bearer {token_a}"},
        json={
            "action_key": "portfolio_review",
            "request_key": "empty-target-preview",
        },
    )
    assert empty_selection_response.status_code == 400
    assert (
        empty_selection_response.json()["errors"][0]["details"]["reason_code"]
        == "explicit_target_selection_required"
    )

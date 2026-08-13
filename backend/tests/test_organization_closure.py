import json
import uuid
from datetime import UTC, datetime, timedelta

from app.models.audit_log import AuditLog
from app.models.data_connection import DataConnection
from app.models.data_governance import (
    OrganizationClosureRequest,
    OrganizationDeletionTombstone,
)
from app.models.organization import Organization
from app.models.organization_provider_credential import OrganizationProviderCredential
from app.models.platform_job import PlatformJob
from app.models.user import User
from app.services.organization_closure_service import (
    finalize_due_organization_closures,
    place_organization_legal_hold,
    release_organization_legal_hold,
    request_organization_closure,
)
from app.services.data_connections_service import mark_sync_failed


def _login(client, email: str, password: str) -> tuple[str, str | None]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    payload = response.json()["data"]
    return payload["access_token"], payload["user"].get("organization_id")


def _create_connection(client, token: str, organization_id: str) -> str:
    headers = {"Authorization": f"Bearer {token}"}
    location = client.post(
        f"/api/v1/organizations/{organization_id}/business-locations",
        headers=headers,
        json={"name": "Closure Test", "domain": "closure.example"},
    )
    assert location.status_code == 200
    campaign = client.post(
        "/api/v1/campaigns",
        headers=headers,
        json={
            "name": "Closure Test",
            "domain": "closure.example",
            "business_location_id": location.json()["data"]["business_location"]["id"],
        },
    )
    assert campaign.status_code == 200
    campaign_id = campaign.json()["data"]["id"]
    mapping = client.put(
        (
            f"/api/v1/organizations/{organization_id}/data-connections/"
            f"google-search-console/mappings/{campaign_id}"
        ),
        headers=headers,
        json={
            "external_resource_id": "sc-domain:closure.example",
            "external_resource_name": "closure.example",
        },
    )
    assert mapping.status_code == 200
    return mapping.json()["data"]["connection"]["id"]


def test_owner_schedules_recoverable_closure_and_can_reopen(client, db_session) -> None:
    token, organization_id = _login(client, "org-owner@example.com", "pass-org-owner")
    assert organization_id is not None
    connection_id = _create_connection(client, token, organization_id)
    connection = db_session.get(DataConnection, connection_id)
    assert connection is not None
    connection.status = "current"
    connection.next_sync_at = datetime.now(UTC) + timedelta(hours=6)
    queued_job = PlatformJob(
        tenant_id=organization_id,
        job_type="rank.schedule_window",
        entity_type="organization",
        entity_id=organization_id,
        idempotency_key=f"closure-{uuid.uuid4()}",
        status="queued",
        payload={"organization_id": organization_id},
        available_at=datetime.now(UTC),
    )
    db_session.add(queued_job)
    db_session.commit()

    headers = {"Authorization": f"Bearer {token}"}
    preview = client.get(
        f"/api/v1/organizations/{organization_id}/data-governance/closures/preview",
        headers=headers,
    )
    assert preview.status_code == 200
    preview_data = preview.json()["data"]["preview"]
    assert preview_data["recovery_days"] == 30
    assert preview_data["affected_counts"]["active_connections"] == 1
    assert preview_data["affected_counts"]["queued_jobs"] == 1
    assert preview_data["confirmation_text"] == "Delete"
    assert preview_data["confirmation_steps"] == 2

    rejected = client.post(
        f"/api/v1/organizations/{organization_id}/data-governance/closures",
        headers=headers,
        json={
            "client_request_id": str(uuid.uuid4()),
            "confirmation": "delete",
            "data_export_choice_acknowledged": True,
            "recovery_window_acknowledged": True,
        },
    )
    assert rejected.status_code == 400

    missing_acknowledgement = client.post(
        f"/api/v1/organizations/{organization_id}/data-governance/closures",
        headers=headers,
        json={
            "client_request_id": str(uuid.uuid4()),
            "confirmation": "Delete",
            "data_export_choice_acknowledged": True,
            "recovery_window_acknowledged": False,
        },
    )
    assert missing_acknowledgement.status_code == 400
    assert missing_acknowledgement.json()["errors"][0]["details"]["reason_code"] == (
        "closure_acknowledgements_required"
    )

    request_id = str(uuid.uuid4())
    scheduled = client.post(
        f"/api/v1/organizations/{organization_id}/data-governance/closures",
        headers=headers,
        json={
            "client_request_id": request_id,
            "confirmation": "Delete",
            "data_export_choice_acknowledged": True,
            "recovery_window_acknowledged": True,
        },
    )
    assert scheduled.status_code == 200
    closure = scheduled.json()["data"]["closure"]
    assert closure["status"] == "recovery_window"
    assert closure["primary_data_deleted"] is False
    assert closure["deletion_authorized"] is True

    replay = client.post(
        f"/api/v1/organizations/{organization_id}/data-governance/closures",
        headers=headers,
        json={
            "client_request_id": request_id,
            "confirmation": "Delete",
            "data_export_choice_acknowledged": True,
            "recovery_window_acknowledged": True,
        },
    )
    assert replay.status_code == 200
    assert replay.json()["data"]["closure"]["id"] == closure["id"]

    db_session.expire_all()
    assert db_session.get(Organization, organization_id).status == "closure_pending"
    assert db_session.get(DataConnection, connection_id).status == "paused_closure"
    assert db_session.get(PlatformJob, queued_job.id).status == "cancelled"

    mark_sync_failed(
        db_session,
        connection_id=connection_id,
        error=RuntimeError("late worker failure"),
    )
    db_session.commit()
    assert db_session.get(DataConnection, connection_id).status == "paused_closure"

    blocked_write = client.post(
        f"/api/v1/organizations/{organization_id}/business-locations",
        headers=headers,
        json={"name": "Blocked", "domain": "blocked.example"},
    )
    assert blocked_write.status_code == 423
    assert (
        blocked_write.json()["errors"][0]["details"]["reason_code"]
        == "organization_closure_read_only"
    )

    reopened = client.post(
        (
            f"/api/v1/organizations/{organization_id}/data-governance/"
            f"closures/{closure['id']}/cancel"
        ),
        headers=headers,
    )
    assert reopened.status_code == 200
    assert reopened.json()["data"]["closure"]["status"] == "cancelled"
    db_session.expire_all()
    assert db_session.get(Organization, organization_id).status == "active"
    assert db_session.get(DataConnection, connection_id).status == "current"
    assert db_session.get(PlatformJob, queued_job.id).status == "cancelled"
    events = {
        row.event_type
        for row in db_session.query(AuditLog).filter(AuditLog.tenant_id == organization_id).all()
    }
    assert "governance.organization_closure.requested" in events
    assert "governance.organization_closure.cancelled" in events


def test_due_closure_waits_for_hold_then_removes_access_and_creates_tombstone(
    client,
    db_session,
) -> None:
    _token, organization_id = _login(client, "org-owner@example.com", "pass-org-owner")
    assert organization_id is not None
    owner = db_session.query(User).filter(User.email == "org-owner@example.com").one()
    platform_owner = db_session.query(User).filter(
        User.email == "platform-owner@example.com"
    ).one()
    started_at = datetime(2026, 6, 1, tzinfo=UTC)
    closure = request_organization_closure(
        db_session,
        tenant_id=organization_id,
        organization_id=organization_id,
        actor_user_id=owner.id,
        client_request_id=str(uuid.uuid4()),
        confirmation="Delete",
        data_export_choice_acknowledged=True,
        recovery_window_acknowledged=True,
        now=started_at,
    )
    db_session.add(
        OrganizationProviderCredential(
            organization_id=organization_id,
            provider_name="mistral",
            auth_mode="api_key",
            encrypted_secret_blob="encrypted-secret",
            key_reference="test-key",
            key_version="v1",
        )
    )
    hold = place_organization_legal_hold(
        db_session,
        organization_id=organization_id,
        actor_user_id=platform_owner.id,
        hold_reference="TEST-HOLD-1",
        reason_summary="Restricted test reason",
        now=started_at + timedelta(days=1),
    )
    db_session.commit()

    held_result = finalize_due_organization_closures(
        db_session,
        now=started_at + timedelta(days=31),
    )
    db_session.commit()
    assert held_result == {
        "closures_finalized": 0,
        "closures_held": 1,
        "closures_authorization_required": 0,
    }
    db_session.expire_all()
    closure_row = db_session.get(OrganizationClosureRequest, closure["id"])
    assert closure_row.status == "on_hold"
    assert db_session.get(Organization, organization_id).status == "closure_pending"

    release_organization_legal_hold(
        db_session,
        legal_hold_id=hold["id"],
        actor_user_id=platform_owner.id,
        now=started_at + timedelta(days=32),
    )
    final_result = finalize_due_organization_closures(
        db_session,
        now=started_at + timedelta(days=32),
    )
    db_session.commit()
    assert final_result == {
        "closures_finalized": 1,
        "closures_held": 0,
        "closures_authorization_required": 0,
    }
    db_session.expire_all()
    assert db_session.get(Organization, organization_id).status == "closed"
    assert db_session.get(OrganizationClosureRequest, closure["id"]).status == (
        "ready_for_verified_deletion"
    )
    assert db_session.query(OrganizationProviderCredential).filter_by(
        organization_id=organization_id
    ).count() == 0
    tombstone = db_session.query(OrganizationDeletionTombstone).filter_by(
        organization_id=organization_id
    ).one()
    assert tombstone.state == "pending_primary_erasure"
    assert tombstone.primary_store_status == "retained_pending_verification"
    assert tombstone.backup_reapply_required is True
    audit = db_session.query(AuditLog).filter(
        AuditLog.event_type == "governance.organization_closure.ready_for_verified_deletion"
    ).one()
    payload = json.loads(audit.payload_json)
    assert payload["primary_store_deleted"] is False
    assert payload["backup_reapply_required"] is True


def test_due_closure_without_durable_authorization_never_advances(client, db_session) -> None:
    _token, organization_id = _login(client, "org-owner@example.com", "pass-org-owner")
    assert organization_id is not None
    owner = db_session.query(User).filter(User.email == "org-owner@example.com").one()
    started_at = datetime(2026, 6, 1, tzinfo=UTC)
    closure = request_organization_closure(
        db_session,
        tenant_id=organization_id,
        organization_id=organization_id,
        actor_user_id=owner.id,
        client_request_id=str(uuid.uuid4()),
        confirmation="Delete",
        data_export_choice_acknowledged=True,
        recovery_window_acknowledged=True,
        now=started_at,
    )
    closure_row = db_session.get(OrganizationClosureRequest, closure["id"])
    assert closure_row is not None
    closure_row.recovery_window_acknowledged = False
    db_session.commit()

    result = finalize_due_organization_closures(
        db_session,
        now=started_at + timedelta(days=31),
    )
    db_session.commit()

    assert result == {
        "closures_finalized": 0,
        "closures_held": 0,
        "closures_authorization_required": 1,
    }
    db_session.expire_all()
    assert db_session.get(OrganizationClosureRequest, closure["id"]).status == "recovery_window"
    assert db_session.get(Organization, organization_id).status == "closure_pending"
    assert db_session.query(OrganizationDeletionTombstone).filter_by(
        organization_id=organization_id
    ).count() == 0


def test_closure_is_owner_only_scoped_and_active_billing_blocks_it(client, db_session) -> None:
    admin_token, admin_org_id = _login(client, "org-admin@example.com", "pass-org-admin")
    owner_token, owner_org_id = _login(client, "org-owner@example.com", "pass-org-owner")
    _other_token, other_org_id = _login(client, "b@example.com", "pass-b")
    assert admin_org_id and owner_org_id and other_org_id
    admin_preview = client.get(
        f"/api/v1/organizations/{admin_org_id}/data-governance/closures/preview",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert admin_preview.status_code == 403
    cross_scope = client.get(
        f"/api/v1/organizations/{other_org_id}/data-governance/closures/preview",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert cross_scope.status_code == 403

    organization = db_session.get(Organization, owner_org_id)
    organization.stripe_subscription_id = "sub_active_test"
    organization.billing_status = "active"
    db_session.commit()
    blocked = client.post(
        f"/api/v1/organizations/{owner_org_id}/data-governance/closures",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "client_request_id": str(uuid.uuid4()),
            "confirmation": "Delete",
            "data_export_choice_acknowledged": True,
            "recovery_window_acknowledged": True,
        },
    )
    assert blocked.status_code == 409
    assert blocked.json()["errors"][0]["details"]["reason_code"] == (
        "closure_active_subscription"
    )


def test_only_platform_owner_can_place_and_release_retention_hold(client) -> None:
    owner_token, organization_id = _login(client, "org-owner@example.com", "pass-org-owner")
    platform_owner_token, _ = _login(
        client,
        "platform-owner@example.com",
        "pass-platform-owner",
    )
    assert organization_id is not None
    payload = {
        "organization_id": organization_id,
        "hold_reference": "LEGAL-2026-1",
        "reason_summary": "Restricted legal reason",
    }
    denied = client.post(
        "/api/v1/platform/data-governance/legal-holds",
        headers={"Authorization": f"Bearer {owner_token}"},
        json=payload,
    )
    assert denied.status_code == 403
    placed = client.post(
        "/api/v1/platform/data-governance/legal-holds",
        headers={"Authorization": f"Bearer {platform_owner_token}"},
        json=payload,
    )
    assert placed.status_code == 200
    hold = placed.json()["data"]["legal_hold"]
    assert hold["status"] == "active"
    assert "reason_summary" not in hold
    released = client.post(
        f"/api/v1/platform/data-governance/legal-holds/{hold['id']}/release",
        headers={"Authorization": f"Bearer {platform_owner_token}"},
    )
    assert released.status_code == 200
    assert released.json()["data"]["legal_hold"]["status"] == "released"

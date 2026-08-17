import base64
import json
import uuid
from datetime import UTC, date, datetime

import pytest

from app.core.settings import get_settings
from app.models.audit_log import AuditLog
from app.models.data_connection import DataConnection
from app.models.data_governance import ProviderDisconnectRequest
from app.models.organization_provider_credential import OrganizationProviderCredential
from app.models.platform_job import PlatformJob
from app.models.search_console_daily_metric import SearchConsoleDailyMetric
from app.services.provider_credentials_service import upsert_organization_provider_credentials


MASTER_KEY_B64 = base64.b64encode(b"0123456789abcdef0123456789abcdef").decode("ascii")


@pytest.fixture(autouse=True)
def _credential_encryption(monkeypatch) -> None:
    monkeypatch.setenv("PLATFORM_MASTER_KEY", MASTER_KEY_B64)
    get_settings.cache_clear()


def _login(client, email: str, password: str) -> tuple[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    payload = response.json()["data"]
    return payload["access_token"], payload["user"]["organization_id"]


def _create_google_connection(client, token: str, organization_id: str) -> tuple[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    location = client.post(
        f"/api/v1/organizations/{organization_id}/business-locations",
        headers=headers,
        json={"name": "Disconnect Test", "domain": "disconnect.example"},
    )
    assert location.status_code == 200
    campaign = client.post(
        "/api/v1/campaigns",
        headers=headers,
        json={
            "name": "Disconnect Test",
            "domain": "disconnect.example",
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
            "external_resource_id": "sc-domain:disconnect.example",
            "external_resource_name": "disconnect.example",
        },
    )
    assert mapping.status_code == 200
    return campaign_id, mapping.json()["data"]["connection"]["id"]


def _save_google_credential(db_session, organization_id: str) -> None:
    upsert_organization_provider_credentials(
        db_session,
        organization_id=organization_id,
        provider_name="google",
        auth_mode="oauth2",
        credentials={
            "access_token": "access-secret",
            "refresh_token": "refresh-secret",
            "expires_at": 2_000_000_000,
            "scope": "https://www.googleapis.com/auth/webmasters.readonly",
        },
    )


def test_owner_disconnects_google_and_preserves_saved_results(
    client,
    db_session,
    monkeypatch,
) -> None:
    token, organization_id = _login(client, "org-owner@example.com", "pass-org-owner")
    campaign_id, connection_id = _create_google_connection(
        client,
        token,
        organization_id,
    )
    _save_google_credential(db_session, organization_id)
    connection = db_session.get(DataConnection, connection_id)
    assert connection is not None
    connection.sync_cursor = {"last_metric_date": "2026-08-12"}
    connection.connection_metadata = {"website_event_ingest_key_hash": "secret-hash"}
    db_session.add(
        SearchConsoleDailyMetric(
            organization_id=organization_id,
            campaign_id=campaign_id,
            metric_date=date(2026, 8, 12),
            clicks=3,
            impressions=100,
            avg_position=8.0,
            deterministic_hash="d" * 64,
        )
    )
    queued_job = PlatformJob(
        tenant_id=connection.tenant_id,
        job_type="data_connections.search_console_sync",
        entity_type="data_connection",
        entity_id=connection.id,
        idempotency_key=f"disconnect-test-{uuid.uuid4()}",
        status="queued",
        payload={"connection_id": connection.id},
        available_at=datetime.now(UTC),
    )
    db_session.add(queued_job)
    db_session.commit()

    preview = client.get(
        (
            f"/api/v1/organizations/{organization_id}/data-governance/"
            "provider-disconnects/google/preview"
        ),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert preview.status_code == 200
    preview_data = preview.json()["data"]["preview"]
    assert preview_data["credential_present"] is True
    assert preview_data["active_connections"] == 1
    assert preview_data["preserved_record_counts"]["search_console_measurements"] == 1
    assert "refresh-secret" not in preview.text

    rejected = client.post(
        f"/api/v1/organizations/{organization_id}/data-governance/provider-disconnects",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "client_request_id": str(uuid.uuid4()),
            "provider_name": "google",
            "confirmation": "disconnect",
        },
    )
    assert rejected.status_code == 400
    assert db_session.query(OrganizationProviderCredential).filter_by(
        organization_id=organization_id,
        provider_name="google",
    ).count() == 1

    revoked_tokens: list[str] = []

    def _confirm_revoke(value: str) -> tuple[str, None]:
        revoked_tokens.append(value)
        return "confirmed", None

    monkeypatch.setattr(
        "app.services.provider_disconnect_service._revoke_google_grant",
        _confirm_revoke,
    )
    request_id = str(uuid.uuid4())
    response = client.post(
        f"/api/v1/organizations/{organization_id}/data-governance/provider-disconnects",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "client_request_id": request_id,
            "provider_name": "google",
            "confirmation": "DISCONNECT GOOGLE",
        },
    )
    assert response.status_code == 200
    result = response.json()["data"]["disconnect"]
    assert result["status"] == "completed"
    assert result["credential_deleted"] is True
    assert result["external_revocation_status"] == "confirmed"
    assert result["connections_disconnected"] == 1
    assert result["queued_jobs_cancelled"] == 1
    assert result["preserved_record_counts"]["search_console_measurements"] == 1
    assert revoked_tokens == ["refresh-secret"]
    assert "refresh-secret" not in response.text
    assert "access-secret" not in response.text

    replay = client.post(
        f"/api/v1/organizations/{organization_id}/data-governance/provider-disconnects",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "client_request_id": request_id,
            "provider_name": "google",
            "confirmation": "DISCONNECT GOOGLE",
        },
    )
    assert replay.status_code == 200
    assert replay.json()["data"]["disconnect"]["id"] == result["id"]
    assert revoked_tokens == ["refresh-secret"]

    db_session.expire_all()
    assert db_session.query(OrganizationProviderCredential).filter_by(
        organization_id=organization_id,
        provider_name="google",
    ).count() == 0
    saved_connection = db_session.get(DataConnection, connection_id)
    assert saved_connection is not None
    assert saved_connection.status == "disconnected"
    assert saved_connection.next_sync_at is None
    assert saved_connection.sync_cursor == {}
    assert saved_connection.connection_metadata == {}
    assert db_session.get(PlatformJob, queued_job.id).status == "cancelled"
    assert db_session.query(SearchConsoleDailyMetric).filter_by(
        organization_id=organization_id,
        campaign_id=campaign_id,
    ).count() == 1
    assert db_session.query(ProviderDisconnectRequest).filter_by(
        organization_id=organization_id,
    ).count() == 1
    audit = (
        db_session.query(AuditLog)
        .filter(AuditLog.event_type == "governance.provider_disconnected")
        .one()
    )
    audit_payload = json.loads(audit.payload_json)
    assert audit_payload["credential_deleted"] is True
    assert "refresh-secret" not in audit.payload_json

    connections = client.get(
        f"/api/v1/organizations/{organization_id}/data-connections",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert connections.status_code == 200
    assert connections.json()["data"]["google_oauth"]["connected"] is False


def test_failed_external_revoke_still_deletes_local_credential(
    client,
    db_session,
    monkeypatch,
) -> None:
    token, organization_id = _login(client, "org-owner@example.com", "pass-org-owner")
    _save_google_credential(db_session, organization_id)
    monkeypatch.setattr(
        "app.services.provider_disconnect_service._revoke_google_grant",
        lambda _token: ("not_confirmed", "google_revoke_unreachable"),
    )

    response = client.post(
        f"/api/v1/organizations/{organization_id}/data-governance/provider-disconnects",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "client_request_id": str(uuid.uuid4()),
            "provider_name": "google",
            "confirmation": "DISCONNECT GOOGLE",
        },
    )
    assert response.status_code == 200
    result = response.json()["data"]["disconnect"]
    assert result["status"] == "completed_external_action_required"
    assert result["credential_deleted"] is True
    assert result["external_revocation_status"] == "not_confirmed"
    assert result["external_revocation_code"] == "google_revoke_unreachable"
    db_session.expire_all()
    assert db_session.query(OrganizationProviderCredential).filter_by(
        organization_id=organization_id,
        provider_name="google",
    ).count() == 0


def test_provider_disconnect_is_owner_only_and_organization_scoped(client) -> None:
    admin_token, admin_org_id = _login(client, "org-admin@example.com", "pass-org-admin")
    owner_token, _owner_org_id = _login(client, "org-owner@example.com", "pass-org-owner")
    _other_token, other_org_id = _login(client, "b@example.com", "pass-b")

    admin_attempt = client.get(
        (
            f"/api/v1/organizations/{admin_org_id}/data-governance/"
            "provider-disconnects/google/preview"
        ),
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert admin_attempt.status_code == 403
    cross_scope = client.get(
        (
            f"/api/v1/organizations/{other_org_id}/data-governance/"
            "provider-disconnects/google/preview"
        ),
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert cross_scope.status_code == 403


def test_late_sync_failure_cannot_reactivate_disconnected_connection(
    client,
    db_session,
) -> None:
    token, organization_id = _login(client, "org-owner@example.com", "pass-org-owner")
    _campaign_id, connection_id = _create_google_connection(
        client,
        token,
        organization_id,
    )
    connection = db_session.get(DataConnection, connection_id)
    assert connection is not None
    connection.status = "disconnected"
    db_session.commit()

    from app.services.data_connections_service import mark_sync_failed

    mark_sync_failed(
        db_session,
        connection_id=connection_id,
        error=RuntimeError("late worker failure"),
    )
    db_session.commit()
    db_session.refresh(connection)
    assert connection.status == "disconnected"
    assert connection.last_error_code is None

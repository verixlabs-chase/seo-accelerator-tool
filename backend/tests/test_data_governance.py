import json
import uuid
from datetime import UTC, datetime, timedelta

from app.models.audit_log import AuditLog
from app.models.data_governance import DataExportRequest
from app.services.data_governance_service import expire_data_export_artifacts


def _login(client, email: str, password: str) -> tuple[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    payload = response.json()["data"]
    return payload["access_token"], payload["user"]["organization_id"]


def test_owner_can_create_idempotent_credential_safe_account_export(client, db_session) -> None:
    token, org_id = _login(client, "org-owner@example.com", "pass-org-owner")
    location = client.post(
        f"/api/v1/organizations/{org_id}/business-locations",
        json={"name": "Export Location", "domain": "export.example"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert location.status_code == 200
    request_id = str(uuid.uuid4())
    body = {"client_request_id": request_id}

    created = client.post(
        f"/api/v1/organizations/{org_id}/data-governance/exports",
        json=body,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert created.status_code == 200
    export = created.json()["data"]["export"]
    assert export["status"] == "ready"
    assert export["download_available"] is True
    assert export["schema_version"] == "gov1.customer-export.v1"
    assert export["record_counts"]["locations"] == 1
    assert len(export["artifact_sha256"]) == 64

    retried = client.post(
        f"/api/v1/organizations/{org_id}/data-governance/exports",
        json=body,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert retried.status_code == 200
    assert retried.json()["data"]["export"]["id"] == export["id"]
    assert db_session.query(DataExportRequest).filter_by(organization_id=org_id).count() == 1

    downloaded = client.get(
        f"/api/v1/organizations/{org_id}/data-governance/exports/{export['id']}/download",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert downloaded.status_code == 200
    assert downloaded.headers["cache-control"] == "private, no-store"
    assert "attachment" in downloaded.headers["content-disposition"]
    payload = downloaded.json()
    assert payload["organization_id"] == org_id
    assert payload["data"]["locations"][0]["name"] == "Export Location"
    member_emails = {member["email"] for member in payload["data"]["members"]}
    assert "org-owner@example.com" in member_emails
    assert "password_hash" not in downloaded.text
    assert "stripe_customer_id" not in downloaded.text
    assert "encrypted_secret_blob" not in downloaded.text
    assert "content_blob" not in downloaded.text
    assert "OAuth and provider credentials" in payload["excluded_data"]

    db_session.expire_all()
    export_row = db_session.query(DataExportRequest).filter_by(id=export["id"]).one()
    assert export_row.downloaded_at is not None
    events = {
        row.event_type
        for row in db_session.query(AuditLog)
        .filter(AuditLog.tenant_id == org_id)
        .all()
    }
    assert "governance.data_export.ready" in events
    assert "governance.data_export.downloaded" in events


def test_data_export_is_owner_only_and_organization_scoped(client) -> None:
    admin_token, admin_org_id = _login(client, "org-admin@example.com", "pass-org-admin")
    owner_token, _owner_org_id = _login(client, "org-owner@example.com", "pass-org-owner")
    _other_token, other_org_id = _login(client, "b@example.com", "pass-b")

    admin_attempt = client.get(
        f"/api/v1/organizations/{admin_org_id}/data-governance/exports",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert admin_attempt.status_code == 403
    cross_org = client.get(
        f"/api/v1/organizations/{other_org_id}/data-governance/exports",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert cross_org.status_code == 403


def test_expired_data_export_artifact_is_removed_but_audit_record_remains(
    client, db_session
) -> None:
    token, org_id = _login(client, "org-owner@example.com", "pass-org-owner")
    created = client.post(
        f"/api/v1/organizations/{org_id}/data-governance/exports",
        json={"client_request_id": str(uuid.uuid4())},
        headers={"Authorization": f"Bearer {token}"},
    )
    export_id = created.json()["data"]["export"]["id"]
    row = db_session.query(DataExportRequest).filter_by(id=export_id).one()
    row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db_session.commit()

    result = expire_data_export_artifacts(db_session)
    db_session.commit()
    assert result == {"artifacts_expired": 1}
    db_session.expire_all()
    row = db_session.query(DataExportRequest).filter_by(id=export_id).one()
    assert row.status == "expired"
    assert row.artifact_content is None
    assert row.artifact_sha256 is not None

    download = client.get(
        f"/api/v1/organizations/{org_id}/data-governance/exports/{export_id}/download",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert download.status_code == 410
    assert (
        download.json()["errors"][0]["details"]["reason_code"]
        == "data_export_expired"
    )


def test_export_document_is_valid_json_in_storage(client, db_session) -> None:
    token, org_id = _login(client, "org-owner@example.com", "pass-org-owner")
    created = client.post(
        f"/api/v1/organizations/{org_id}/data-governance/exports",
        json={"client_request_id": str(uuid.uuid4())},
        headers={"Authorization": f"Bearer {token}"},
    )
    export_id = created.json()["data"]["export"]["id"]
    row = db_session.query(DataExportRequest).filter_by(id=export_id).one()
    payload = json.loads(row.artifact_content or "")
    assert payload["schema_version"] == row.schema_version
    assert payload["record_counts"] == row.record_counts

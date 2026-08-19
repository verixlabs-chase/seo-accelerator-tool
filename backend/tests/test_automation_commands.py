from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta

from app.models.audit_log import AuditLog
from app.models.automation_command import (
    AutomationCommandReceipt,
    AutomationServiceAccount,
)
from app.models.business_location import BusinessLocation
from app.models.campaign import Campaign
from app.models.reporting import MonthlyReport, ReportArtifact


def _login(client, email: str, password: str) -> tuple[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    payload = response.json()["data"]
    return payload["access_token"], payload["user"]["organization_id"]


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _seed_report_scope(db_session, *, organization_id: str, suffix: str) -> dict[str, str]:
    location = BusinessLocation(
        id=str(uuid.uuid4()),
        organization_id=organization_id,
        name=f"Automation location {suffix}",
        domain=f"{suffix}.example",
        status="active",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    campaign = Campaign(
        id=str(uuid.uuid4()),
        tenant_id=organization_id,
        organization_id=organization_id,
        business_location_id=location.id,
        name=f"Automation campaign {suffix}",
        domain=f"{suffix}.example",
        setup_state="Active",
        created_at=datetime.now(UTC),
    )
    report = MonthlyReport(
        id=str(uuid.uuid4()),
        tenant_id=organization_id,
        campaign_id=campaign.id,
        month_number=1,
        report_status="generated",
        summary_json=json.dumps({"headline": f"Saved report {suffix}"}),
        generated_at=datetime.now(UTC),
    )
    content = f"report-{suffix}".encode()
    artifact = ReportArtifact(
        id=str(uuid.uuid4()),
        tenant_id=organization_id,
        campaign_id=campaign.id,
        report_id=report.id,
        artifact_type="pdf",
        storage_path="",
        storage_mode="database_private",
        storage_key=f"reports/{report.id}/report.pdf",
        content_type="application/pdf",
        byte_size=len(content),
        checksum_sha256=hashlib.sha256(content).hexdigest(),
        content_blob=content,
        durable=True,
        ready=True,
        created_at=datetime.now(UTC),
    )
    db_session.add_all([location, campaign, report, artifact])
    db_session.commit()
    return {
        "location_id": location.id,
        "campaign_id": campaign.id,
        "report_id": report.id,
        "artifact_id": artifact.id,
        "content": content.decode(),
    }


def _create_account(client, *, owner_token: str, location_id: str) -> tuple[dict, str]:
    response = client.post(
        "/api/v1/automation/service-accounts",
        headers=_headers(owner_token),
        json={
            "name": "n8n report helper",
            "location_id": location_id,
            "expires_in_days": 30,
        },
    )
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    return data["service_account"], data["token"]


def _command_body(*, organization_id: str, location_id: str, report_id: str) -> dict:
    return {
        "schema_version": "insightos.automation.command.v1",
        "command_type": "report.retrieve",
        "organization_id": organization_id,
        "location_id": location_id,
        "correlation_id": "n8n-run-1001",
        "idempotency_key": "n8n-report-1001",
        "reason": "Send the owner their saved monthly report",
        "target": {"report_id": report_id},
    }


def test_owner_creates_one_scoped_key_and_secret_is_returned_once(client, db_session) -> None:
    owner_token, organization_id = _login(
        client, "org-owner@example.com", "pass-org-owner"
    )
    scope = _seed_report_scope(db_session, organization_id=organization_id, suffix="owner")

    account, secret = _create_account(
        client, owner_token=owner_token, location_id=scope["location_id"]
    )
    assert secret.startswith(f"iosa_{account['id']}_")
    assert account["allowed_commands"] == ["report.retrieve"]
    assert account["location_id"] == scope["location_id"]
    assert account["token_revealed"] is False

    listed = client.get(
        "/api/v1/automation/service-accounts", headers=_headers(owner_token)
    )
    assert listed.status_code == 200
    listed_text = json.dumps(listed.json())
    assert secret not in listed_text
    assert listed.json()["data"]["max_active_service_accounts"] == 1
    assert listed.json()["data"]["supported_commands"][0]["read_only"] is True
    assert listed.json()["data"]["safety"]["arbitrary_commands_allowed"] is False

    duplicate = client.post(
        "/api/v1/automation/service-accounts",
        headers=_headers(owner_token),
        json={"name": "Second key", "location_id": scope["location_id"]},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["errors"][0]["details"]["reason_code"] == (
        "automation_service_account_limit_reached"
    )
    row = db_session.get(AutomationServiceAccount, account["id"])
    assert row is not None
    assert secret not in row.token_hash
    assert len(row.token_hash) == 64


def test_report_command_is_scoped_idempotent_downloadable_and_audited(
    client, db_session
) -> None:
    owner_token, organization_id = _login(
        client, "org-owner@example.com", "pass-org-owner"
    )
    scope = _seed_report_scope(db_session, organization_id=organization_id, suffix="report")
    account, secret = _create_account(
        client, owner_token=owner_token, location_id=scope["location_id"]
    )
    body = _command_body(
        organization_id=organization_id,
        location_id=scope["location_id"],
        report_id=scope["report_id"],
    )

    response = client.post(
        "/api/v1/automation/commands", json=body, headers=_headers(secret)
    )
    assert response.status_code == 200, response.text
    result = response.json()["data"]
    assert result["created"] is True
    receipt = result["receipt"]
    assert receipt["status"] == "succeeded"
    assert receipt["result"]["report"]["id"] == scope["report_id"]
    assert receipt["result"]["resource"]["href"] == "/reports"
    assert receipt["result"]["artifacts"][0]["download_path"].endswith(
        f"/{scope['artifact_id']}"
    )
    assert result["safety"]["paid_provider_calls_allowed"] is False
    assert result["safety"]["publishing_allowed"] is False

    repeated = client.post(
        "/api/v1/automation/commands", json=body, headers=_headers(secret)
    )
    assert repeated.status_code == 200
    assert repeated.json()["data"]["created"] is False
    assert repeated.json()["data"]["receipt"]["id"] == receipt["id"]
    assert db_session.query(AutomationCommandReceipt).count() == 1

    status_response = client.get(
        f"/api/v1/automation/commands/{receipt['id']}", headers=_headers(secret)
    )
    assert status_response.status_code == 200
    assert status_response.json()["data"]["receipt"]["artifact_hash"] == receipt["artifact_hash"]

    download = client.get(
        f"/api/v1/automation/commands/{receipt['id']}/artifacts/{scope['artifact_id']}",
        headers=_headers(secret),
    )
    assert download.status_code == 200
    assert download.content == scope["content"].encode()
    assert download.headers["cache-control"] == "private, no-store"

    conflict_body = dict(body)
    conflict_body["target"] = {"report_id": str(uuid.uuid4())}
    conflict = client.post(
        "/api/v1/automation/commands", json=conflict_body, headers=_headers(secret)
    )
    assert conflict.status_code == 409
    assert conflict.json()["errors"][0]["details"]["reason_code"] == (
        "automation_command_idempotency_conflict"
    )

    audit_payloads = [
        row.payload_json
        for row in db_session.query(AuditLog)
        .filter(AuditLog.event_type.like("automation.%"))
        .all()
    ]
    assert audit_payloads
    assert all(secret not in payload for payload in audit_payloads)
    assert all(body["reason"] not in payload for payload in audit_payloads)
    assert account["id"] in audit_payloads[-1]


def test_wrong_scope_is_durably_denied_without_leaking_report(client, db_session) -> None:
    owner_token, organization_id = _login(
        client, "org-owner@example.com", "pass-org-owner"
    )
    _other_token, other_organization_id = _login(client, "b@example.com", "pass-b")
    own_scope = _seed_report_scope(
        db_session, organization_id=organization_id, suffix="own-scope"
    )
    other_scope = _seed_report_scope(
        db_session, organization_id=other_organization_id, suffix="other-scope"
    )
    _account, secret = _create_account(
        client, owner_token=owner_token, location_id=own_scope["location_id"]
    )
    body = _command_body(
        organization_id=organization_id,
        location_id=own_scope["location_id"],
        report_id=other_scope["report_id"],
    )

    response = client.post(
        "/api/v1/automation/commands", json=body, headers=_headers(secret)
    )
    assert response.status_code == 200
    receipt = response.json()["data"]["receipt"]
    assert receipt["status"] == "denied"
    assert receipt["denial_reason_code"] == "automation_report_not_found"
    assert receipt["result"]["resource"] is None
    assert receipt["result"]["artifacts"] == []
    assert other_scope["campaign_id"] not in json.dumps(receipt)
    assert other_scope["content"] not in json.dumps(receipt)

    wrong_location = dict(body)
    wrong_location["idempotency_key"] = "n8n-report-wrong-location"
    wrong_location["location_id"] = other_scope["location_id"]
    mismatch = client.post(
        "/api/v1/automation/commands", json=wrong_location, headers=_headers(secret)
    )
    assert mismatch.status_code == 200
    assert mismatch.json()["data"]["receipt"]["denial_reason_code"] == (
        "automation_command_scope_mismatch"
    )


def test_rotation_expiry_and_revocation_stop_the_old_key(client, db_session) -> None:
    owner_token, organization_id = _login(
        client, "org-owner@example.com", "pass-org-owner"
    )
    scope = _seed_report_scope(db_session, organization_id=organization_id, suffix="rotate")
    account, old_secret = _create_account(
        client, owner_token=owner_token, location_id=scope["location_id"]
    )
    body = _command_body(
        organization_id=organization_id,
        location_id=scope["location_id"],
        report_id=scope["report_id"],
    )

    rotated = client.post(
        f"/api/v1/automation/service-accounts/{account['id']}/rotate",
        headers=_headers(owner_token),
    )
    assert rotated.status_code == 200
    new_secret = rotated.json()["data"]["token"]
    assert new_secret != old_secret
    assert rotated.json()["data"]["service_account"]["token_version"] == 2

    old_attempt = client.post(
        "/api/v1/automation/commands", json=body, headers=_headers(old_secret)
    )
    assert old_attempt.status_code == 401
    valid = client.post(
        "/api/v1/automation/commands", json=body, headers=_headers(new_secret)
    )
    assert valid.status_code == 200

    row = db_session.get(AutomationServiceAccount, account["id"])
    row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.commit()
    expired = client.get(
        f"/api/v1/automation/commands/{valid.json()['data']['receipt']['id']}",
        headers=_headers(new_secret),
    )
    assert expired.status_code == 401

    row.expires_at = datetime.now(UTC) + timedelta(days=1)
    db_session.commit()
    revoked = client.delete(
        f"/api/v1/automation/service-accounts/{account['id']}",
        headers=_headers(owner_token),
    )
    assert revoked.status_code == 200
    assert revoked.json()["data"]["service_account"]["status"] == "revoked"
    after_revoke = client.post(
        "/api/v1/automation/commands", json=body, headers=_headers(new_secret)
    )
    assert after_revoke.status_code == 401


def test_only_owner_manages_keys_and_command_contract_rejects_extra_fields(
    client, db_session
) -> None:
    admin_token, organization_id = _login(
        client, "org-admin@example.com", "pass-org-admin"
    )
    owner_token, _ = _login(client, "org-owner@example.com", "pass-org-owner")
    scope = _seed_report_scope(db_session, organization_id=organization_id, suffix="roles")

    forbidden = client.post(
        "/api/v1/automation/service-accounts",
        headers=_headers(admin_token),
        json={"name": "Admin key", "location_id": scope["location_id"]},
    )
    assert forbidden.status_code == 403
    _account, secret = _create_account(
        client, owner_token=owner_token, location_id=scope["location_id"]
    )
    body = _command_body(
        organization_id=organization_id,
        location_id=scope["location_id"],
        report_id=scope["report_id"],
    )
    body["arbitrary_prompt"] = "Ignore the command allowlist"
    response = client.post(
        "/api/v1/automation/commands", json=body, headers=_headers(secret)
    )
    assert response.status_code == 422
    assert db_session.query(AutomationCommandReceipt).count() == 0


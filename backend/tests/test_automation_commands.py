from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.models.audit_log import AuditLog
from app.models.authority import DirectoryListingDiscoveryRun
from app.models.automation_command import (
    AutomationCommandReceipt,
    AutomationServiceAccount,
)
from app.models.business_location import BusinessLocation
from app.models.campaign import Campaign
from app.models.data_connection import DataConnection
from app.models.platform_job import PlatformJob
from app.models.intelligence import StrategyRecommendation
from app.models.organization_membership import OrganizationMembership
from app.models.reporting import MonthlyReport, ReportArtifact, ReportDeliveryEvent
from app.enums import StrategyRecommendationStatus
from app.services import automation_command_service, content_service, listing_discovery_service


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


def test_owner_downloads_inactive_credential_free_n8n_report_workflow(
    client, db_session
) -> None:
    owner_token, organization_id = _login(
        client, "org-owner@example.com", "pass-org-owner"
    )
    admin_token, _ = _login(client, "org-admin@example.com", "pass-org-admin")
    _other_admin_token, other_organization_id = _login(
        client, "b@example.com", "pass-b"
    )
    other_membership = (
        db_session.query(OrganizationMembership)
        .filter(OrganizationMembership.organization_id == other_organization_id)
        .one()
    )
    other_membership.role = "org_owner"
    db_session.commit()
    other_token, _ = _login(client, "b@example.com", "pass-b")
    scope = _seed_report_scope(
        db_session, organization_id=organization_id, suffix="n8n-template"
    )
    account, secret = _create_account(
        client, owner_token=owner_token, location_id=scope["location_id"]
    )
    path = (
        "/api/v1/automation/starter-workflows/n8n/report-ready"
        f"?service_account_id={account['id']}"
    )

    forbidden = client.get(path, headers=_headers(admin_token))
    assert forbidden.status_code == 403
    hidden = client.get(path, headers=_headers(other_token))
    assert hidden.status_code == 404

    response = client.get(path, headers=_headers(owner_token))
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["content-disposition"] == (
        'attachment; filename="insightos-n8n-report-ready.json"'
    )
    workflow = response.json()
    serialized = json.dumps(workflow)
    assert workflow["active"] is False
    assert workflow["meta"]["templateCredsSetupCompleted"] is False
    assert workflow["meta"]["insightosTemplateVersion"] == (
        "insightos.n8n.report-ready.v1"
    )
    assert secret not in serialized
    assert "iosa_" not in serialized
    assert "arbitrary_prompt" not in serialized
    assert "wordpress.publish" not in serialized

    nodes = {node["name"]: node for node in workflow["nodes"]}
    assert set(node["type"] for node in workflow["nodes"]) <= {
        "n8n-nodes-base.webhook",
        "n8n-nodes-base.if",
        "n8n-nodes-base.httpRequest",
        "n8n-nodes-base.noOp",
        "n8n-nodes-base.stickyNote",
    }
    report_filter = nodes["Use only this location's reports"]
    right_values = {
        condition["rightValue"]
        for condition in report_filter["parameters"]["conditions"]["conditions"]
    }
    assert {
        "insightos.automation.event.v1",
        "report.ready",
        "ready",
        "report",
        organization_id,
        scope["location_id"],
    } <= right_values

    request = nodes["Retrieve the saved report"]
    parameters = request["parameters"]
    assert parameters["url"] == "http://testserver/api/v1/automation/commands"
    assert parameters["authentication"] == "genericCredentialType"
    assert parameters["genericAuthType"] == "httpBearerAuth"
    assert parameters["contentType"] == "json"
    assert "credentials" not in request
    assert organization_id in parameters["jsonBody"]
    assert scope["location_id"] in parameters["jsonBody"]
    assert "$json.body.resource.id" in parameters["jsonBody"]
    assert "'n8n:' + $json.body.event_id" in parameters["jsonBody"]
    assert "'report-ready:' + $json.body.event_id" in parameters["jsonBody"]
    assert workflow["connections"]["Receive a saved report update"]["main"]


def test_owner_downloads_inactive_monthly_saved_report_workflow_only_after_opt_in(
    client, db_session
) -> None:
    owner_token, organization_id = _login(
        client, "org-owner@example.com", "pass-org-owner"
    )
    scope = _seed_report_scope(
        db_session, organization_id=organization_id, suffix="n8n-monthly"
    )
    account, secret = _create_account(
        client, owner_token=owner_token, location_id=scope["location_id"]
    )
    path = (
        "/api/v1/automation/starter-workflows/n8n/saved-report-schedule"
        f"?service_account_id={account['id']}&campaign_id={scope['campaign_id']}"
    )
    blocked = client.get(path, headers=_headers(owner_token))
    assert blocked.status_code == 409
    assert blocked.json()["errors"][0]["details"]["reason_code"] == (
        "automation_command_not_allowed"
    )

    rotated = client.post(
        f"/api/v1/automation/service-accounts/{account['id']}/rotate",
        headers=_headers(owner_token),
        json={
            "allowed_commands": ["report.retrieve", "report.generate_saved"]
        },
    )
    assert rotated.status_code == 200
    replacement_secret = rotated.json()["data"]["token"]
    response = client.get(path, headers=_headers(owner_token))
    assert response.status_code == 200, response.text
    assert response.headers["content-disposition"] == (
        'attachment; filename="insightos-n8n-monthly-private-report.json"'
    )
    workflow = response.json()
    serialized = json.dumps(workflow)
    assert workflow["active"] is False
    assert workflow["meta"]["templateCredsSetupCompleted"] is False
    assert workflow["meta"]["insightosTemplateVersion"] == (
        "insightos.n8n.saved-report-schedule.v1"
    )
    assert secret not in serialized
    assert replacement_secret not in serialized
    assert "iosa_" not in serialized

    nodes = {node["name"]: node for node in workflow["nodes"]}
    schedule = nodes["Once a month"]
    assert schedule["type"] == "n8n-nodes-base.scheduleTrigger"
    interval = schedule["parameters"]["rule"]["interval"][0]
    assert interval == {
        "field": "months",
        "monthsInterval": 1,
        "triggerAtDayOfMonth": 1,
        "triggerAtHour": 9,
        "triggerAtMinute": 0,
    }
    command = nodes["Create a private report from saved results"]
    assert command["type"] == "n8n-nodes-base.httpRequest"
    assert command["parameters"]["authentication"] == "genericCredentialType"
    assert command["parameters"]["genericAuthType"] == "httpBearerAuth"
    assert scope["campaign_id"] in command["parameters"]["jsonBody"]
    assert "report.generate_saved" in command["parameters"]["jsonBody"]
    assert "$now.toFormat('yyyy-MM')" in command["parameters"]["jsonBody"]
    assert set(node["type"] for node in workflow["nodes"]) <= {
        "n8n-nodes-base.scheduleTrigger",
        "n8n-nodes-base.httpRequest",
        "n8n-nodes-base.noOp",
        "n8n-nodes-base.stickyNote",
    }


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


def test_owner_expands_scope_by_rotating_key_and_n8n_generates_one_private_report(
    client, db_session
) -> None:
    owner_token, organization_id = _login(
        client, "org-owner@example.com", "pass-org-owner"
    )
    scope = _seed_report_scope(
        db_session, organization_id=organization_id, suffix="saved-generation"
    )
    account, read_only_secret = _create_account(
        client, owner_token=owner_token, location_id=scope["location_id"]
    )
    body = {
        "schema_version": "insightos.automation.command.v1",
        "command_type": "report.generate_saved",
        "organization_id": organization_id,
        "location_id": scope["location_id"],
        "correlation_id": "n8n-monthly-report-2026-08",
        "idempotency_key": "saved-report-generation-2026-08",
        "reason": "Create this month's private report from saved results",
        "target": {"campaign_id": scope["campaign_id"]},
    }

    denied = client.post(
        "/api/v1/automation/commands",
        json=body,
        headers=_headers(read_only_secret),
    )
    assert denied.status_code == 200
    assert denied.json()["data"]["receipt"]["denial_reason_code"] == (
        "automation_command_not_allowed"
    )
    reports_before = db_session.query(MonthlyReport).count()

    rotated = client.post(
        f"/api/v1/automation/service-accounts/{account['id']}/rotate",
        headers=_headers(owner_token),
        json={
            "allowed_commands": ["report.retrieve", "report.generate_saved"]
        },
    )
    assert rotated.status_code == 200, rotated.text
    expanded_secret = rotated.json()["data"]["token"]
    assert rotated.json()["data"]["service_account"]["allowed_commands"] == [
        "report.retrieve",
        "report.generate_saved",
    ]
    body["idempotency_key"] = "saved-report-generation-2026-08-expanded"

    generated = client.post(
        "/api/v1/automation/commands",
        json=body,
        headers=_headers(expanded_secret),
    )
    assert generated.status_code == 200, generated.text
    result = generated.json()["data"]
    assert result["created"] is True
    assert result["receipt"]["status"] == "succeeded"
    assert result["receipt"]["command_type"] == "report.generate_saved"
    assert result["receipt"]["result"]["report"]["id"]
    assert result["receipt"]["result"]["resource"]["href"] == "/reports"
    assert result["safety"]["paid_provider_calls_allowed"] is False
    assert result["safety"]["publishing_allowed"] is False
    assert db_session.query(MonthlyReport).count() == reports_before + 1

    repeated = client.post(
        "/api/v1/automation/commands",
        json=body,
        headers=_headers(expanded_secret),
    )
    assert repeated.status_code == 200
    assert repeated.json()["data"]["created"] is False
    assert repeated.json()["data"]["receipt"]["id"] == result["receipt"]["id"]
    assert db_session.query(MonthlyReport).count() == reports_before + 1


def test_recommendation_retrieval_is_explicit_read_only_and_idempotent(
    client, db_session
) -> None:
    owner_token, organization_id = _login(
        client, "org-owner@example.com", "pass-org-owner"
    )
    scope = _seed_report_scope(
        db_session, organization_id=organization_id, suffix="recommendation"
    )
    recommendation = StrategyRecommendation(
        id=str(uuid.uuid4()),
        tenant_id=organization_id,
        campaign_id=scope["campaign_id"],
        recommendation_type="content.refresh",
        rationale="Update the service page so customers can understand the offer.",
        status=StrategyRecommendationStatus.GENERATED,
        evidence_json="[]",
        rollback_plan_json='{"steps":[]}',
    )
    db_session.add(recommendation)
    db_session.commit()
    account, read_only_secret = _create_account(
        client, owner_token=owner_token, location_id=scope["location_id"]
    )
    body = {
        "schema_version": "insightos.automation.command.v1",
        "command_type": "recommendation.retrieve",
        "organization_id": organization_id,
        "location_id": scope["location_id"],
        "correlation_id": "n8n-recommendation-1",
        "idempotency_key": "recommendation-ready-1001",
        "reason": "Send a saved recommendation to the owner's task system",
        "target": {"recommendation_id": recommendation.id},
    }
    denied = client.post(
        "/api/v1/automation/commands", json=body, headers=_headers(read_only_secret)
    )
    assert denied.status_code == 200
    assert denied.json()["data"]["receipt"]["denial_reason_code"] == "automation_command_not_allowed"

    rotated = client.post(
        f"/api/v1/automation/service-accounts/{account['id']}/rotate",
        headers=_headers(owner_token),
        json={"allowed_commands": [
            "report.retrieve",
            "recommendation.retrieve",
            "recommendation.request_review",
        ]},
    )
    assert rotated.status_code == 200, rotated.text
    secret = rotated.json()["data"]["token"]
    body["idempotency_key"] = "recommendation-ready-1002"
    response = client.post(
        "/api/v1/automation/commands", json=body, headers=_headers(secret)
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    result = data["receipt"]["result"]
    assert data["receipt"]["status"] == "succeeded", data
    assert result["resource"] == {
        "type": "recommendation", "id": recommendation.id, "href": "/opportunities"
    }
    assert result["truth"] == {
        "saved_result_only": True,
        "owner_review_required": True,
        "review_requested": False,
        "approved": False,
        "executed": False,
    }
    serialized = json.dumps(result)
    assert "evidence_json" not in serialized
    assert "input_hash" not in serialized
    db_session.refresh(recommendation)
    assert recommendation.status == StrategyRecommendationStatus.GENERATED

    repeated = client.post(
        "/api/v1/automation/commands", json=body, headers=_headers(secret)
    )
    assert repeated.status_code == 200
    assert repeated.json()["data"]["created"] is False
    assert repeated.json()["data"]["receipt"]["id"] == data["receipt"]["id"]

    review_body = {
        **body,
        "command_type": "recommendation.request_review",
        "correlation_id": "n8n-review-1",
        "idempotency_key": "recommendation-review-1002",
        "reason": "Ask the owner to review this saved recommendation",
    }
    review = client.post(
        "/api/v1/automation/commands", json=review_body, headers=_headers(secret)
    )
    assert review.status_code == 200, review.text
    review_result = review.json()["data"]["receipt"]["result"]
    assert review_result["truth"]["review_requested"] is True
    assert review_result["truth"]["approved"] is False
    db_session.refresh(recommendation)
    assert recommendation.status == StrategyRecommendationStatus.GENERATED

    visible = client.get(
        "/api/v1/intelligence/recommendations",
        params={"campaign_id": scope["campaign_id"]},
        headers=_headers(owner_token),
    )
    assert visible.status_code == 200, visible.text
    item = next(item for item in visible.json()["data"]["items"] if item["id"] == recommendation.id)
    assert item["automation_review_request"]["requested"] is True
    assert item["automation_review_request"]["source"] == "connected_workflow"

    starter = client.get(
        "/api/v1/automation/starter-workflows/n8n/recommendation-ready",
        params={"service_account_id": account["id"]},
        headers=_headers(owner_token),
    )
    assert starter.status_code == 200, starter.text
    workflow = starter.json()
    assert workflow["active"] is False
    text = json.dumps(workflow)
    assert "recommendation.ready" in text
    assert "recommendation.retrieve" in text
    assert "recommendation.request_review" in text
    assert scope["location_id"] in text
    assert "recommendation.approve" not in text
    assert "recommendation.execute" not in text
    assert db_session.query(ReportDeliveryEvent).count() == 0

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


def test_scoped_key_queues_one_saved_connection_refresh_and_exposes_job_status(
    client, db_session
) -> None:
    owner_token, organization_id = _login(
        client, "org-owner@example.com", "pass-org-owner"
    )
    scope = _seed_report_scope(
        db_session, organization_id=organization_id, suffix="refresh-command"
    )
    connection = DataConnection(
        id=str(uuid.uuid4()),
        tenant_id=organization_id,
        organization_id=organization_id,
        business_location_id=scope["location_id"],
        campaign_id=scope["campaign_id"],
        provider_name="google_search_console",
        external_resource_id="sc-domain:refresh-command.example",
        external_resource_name="refresh-command.example",
        resource_scope="domain",
        status="connected",
        next_sync_at=datetime.now(UTC),
        sync_cursor={},
        connection_metadata={},
    )
    db_session.add(connection)
    db_session.commit()
    account, initial_secret = _create_account(
        client, owner_token=owner_token, location_id=scope["location_id"]
    )
    rotated = client.post(
        f"/api/v1/automation/service-accounts/{account['id']}/rotate",
        headers=_headers(owner_token),
        json={"allowed_commands": ["report.retrieve", "connection.refresh_saved"]},
    )
    assert rotated.status_code == 200, rotated.text
    secret = rotated.json()["data"]["token"]
    body = {
        "schema_version": "insightos.automation.command.v1",
        "command_type": "connection.refresh_saved",
        "organization_id": organization_id,
        "location_id": scope["location_id"],
        "correlation_id": "n8n-refresh-1",
        "idempotency_key": "n8n-refresh-command-1001",
        "reason": "Refresh saved organic search facts",
        "target": {"connection_id": connection.id},
    }
    denied = client.post(
        "/api/v1/automation/commands", json=body, headers=_headers(initial_secret)
    )
    assert denied.status_code == 401

    response = client.post(
        "/api/v1/automation/commands", json=body, headers=_headers(secret)
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["receipt"]["status"] == "succeeded"
    assert data["receipt"]["result"]["resource"]["id"] == connection.id
    assert data["receipt"]["result"]["job"]["status"] == "queued"
    assert data["receipt"]["result"]["truth"] == {
        "accepted": True,
        "completed": False,
        "publishing_allowed": False,
    }
    assert db_session.query(PlatformJob).count() == 1

    repeated = client.post(
        "/api/v1/automation/commands", json=body, headers=_headers(secret)
    )
    assert repeated.status_code == 200
    assert repeated.json()["data"]["created"] is False
    assert db_session.query(PlatformJob).count() == 1

    job = db_session.get(PlatformJob, data["receipt"]["result"]["job"]["id"])
    job.status = "completed"
    job.finished_at = datetime.now(UTC)
    job.result = {"raw_provider_payload": "must not be exposed"}
    db_session.commit()
    polled = client.get(
        f"/api/v1/automation/commands/{data['receipt']['id']}",
        headers=_headers(secret),
    )
    assert polled.status_code == 200
    polled_job = polled.json()["data"]["receipt"]["result"]["job"]
    assert polled_job["status"] == "completed"
    assert "raw_provider_payload" not in json.dumps(polled.json())


def test_explicit_key_scope_queues_one_priced_public_listing_check(
    client, db_session, monkeypatch
) -> None:
    owner_token, organization_id = _login(
        client, "org-owner@example.com", "pass-org-owner"
    )
    scope = _seed_report_scope(
        db_session, organization_id=organization_id, suffix="priced-listing-command"
    )
    location = db_session.get(BusinessLocation, scope["location_id"])
    location.address_line1 = "100 Main Street"
    location.city = "Reno"
    location.region = "NV"
    location.postal_code = "89501"
    location.country_code = "US"
    location.latitude = 39.5296
    location.longitude = -119.8138
    db_session.commit()
    monkeypatch.setattr(
        listing_discovery_service, "_credential_owner", lambda *_args: "platform"
    )
    account, initial_secret = _create_account(
        client, owner_token=owner_token, location_id=scope["location_id"]
    )
    body = {
        "schema_version": "insightos.automation.command.v1",
        "command_type": "listing.check_public",
        "organization_id": organization_id,
        "location_id": scope["location_id"],
        "correlation_id": "n8n-listings-1",
        "idempotency_key": "n8n-listings-command-1001",
        "reason": "Check supported public listings for this location",
        "target": {"campaign_id": scope["campaign_id"]},
    }
    denied = client.post(
        "/api/v1/automation/commands", json=body, headers=_headers(initial_secret)
    )
    assert denied.status_code == 200
    assert denied.json()["data"]["receipt"]["denial_reason_code"] == "automation_command_not_allowed"
    assert db_session.query(DirectoryListingDiscoveryRun).count() == 0

    rotated = client.post(
        f"/api/v1/automation/service-accounts/{account['id']}/rotate",
        headers=_headers(owner_token),
        json={"allowed_commands": ["report.retrieve", "listing.check_public"]},
    )
    assert rotated.status_code == 200, rotated.text
    secret = rotated.json()["data"]["token"]
    body["idempotency_key"] = "n8n-listings-command-1002"
    response = client.post(
        "/api/v1/automation/commands", json=body, headers=_headers(secret)
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    result = data["receipt"]["result"]
    assert data["receipt"]["status"] == "succeeded", data
    assert result["resource"]["type"] == "public_listing_check"
    assert result["job"]["status"] == "queued"
    assert result["job"]["estimated_credits"] == 2
    assert result["truth"] == {
        "accepted": True,
        "completed": False,
        "uses_allowance": True,
        "publishing_allowed": False,
        "corrections_allowed": False,
    }
    assert db_session.query(DirectoryListingDiscoveryRun).count() == 1

    repeated = client.post(
        "/api/v1/automation/commands", json=body, headers=_headers(secret)
    )
    assert repeated.status_code == 200
    assert repeated.json()["data"]["created"] is False
    assert db_session.query(DirectoryListingDiscoveryRun).count() == 1
    assert "dataforseo" not in json.dumps(data).lower()


def test_workflow_creates_only_private_draft_from_accepted_brief(
    client, db_session, monkeypatch
) -> None:
    owner_token, organization_id = _login(
        client, "org-owner@example.com", "pass-org-owner"
    )
    scope = _seed_report_scope(
        db_session, organization_id=organization_id, suffix="working-draft-command"
    )
    account, initial_secret = _create_account(
        client, owner_token=owner_token, location_id=scope["location_id"]
    )
    brief_id = str(uuid.uuid4())
    draft_id = str(uuid.uuid4())
    calls: list[dict] = []

    def _create_draft(_db, **kwargs):
        calls.append(kwargs)
        return {
            "created": True,
            "item": {
                "id": draft_id,
                "title": "Emergency service page",
                "revision": 1,
                "status": "working",
                "sections": [{"heading": "Explain the service", "body": ""}],
                "automatic_publishing_allowed": False,
            },
        }

    monkeypatch.setattr(content_service, "create_content_draft", _create_draft)
    body = {
        "schema_version": "insightos.automation.command.v1",
        "command_type": "content.create_working_draft",
        "organization_id": organization_id,
        "location_id": scope["location_id"],
        "correlation_id": "n8n-working-draft-1",
        "idempotency_key": "n8n-working-draft-1001",
        "reason": "Start the owner-accepted content brief",
        "target": {"campaign_id": scope["campaign_id"], "brief_id": brief_id},
    }
    denied = client.post(
        "/api/v1/automation/commands", json=body, headers=_headers(initial_secret)
    )
    assert denied.status_code == 200
    assert denied.json()["data"]["receipt"]["denial_reason_code"] == "automation_command_not_allowed"
    assert calls == []

    rotated = client.post(
        f"/api/v1/automation/service-accounts/{account['id']}/rotate",
        headers=_headers(owner_token),
        json={"allowed_commands": ["report.retrieve", "content.create_working_draft"]},
    )
    assert rotated.status_code == 200, rotated.text
    secret = rotated.json()["data"]["token"]
    body["idempotency_key"] = "n8n-working-draft-1002"
    response = client.post(
        "/api/v1/automation/commands", json=body, headers=_headers(secret)
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["receipt"]["status"] == "succeeded"
    assert data["receipt"]["result"]["draft"] == {
        "id": draft_id,
        "brief_id": brief_id,
        "status": "working",
        "title": "Emergency service page",
        "revision": 1,
    }
    assert data["receipt"]["result"]["truth"] == {
        "created": True,
        "owner_review_required": True,
        "approved": False,
        "scheduled": False,
        "published": False,
    }
    assert calls[0]["campaign_id"] == scope["campaign_id"]
    assert calls[0]["brief_id"] == brief_id

    repeated = client.post(
        "/api/v1/automation/commands", json=body, headers=_headers(secret)
    )
    assert repeated.status_code == 200
    assert repeated.json()["data"]["created"] is False
    assert len(calls) == 1
    serialized = json.dumps(data)
    assert "sections" not in serialized
    assert "automatic_publishing_allowed" not in serialized


def test_workflow_requests_owner_review_without_approving_draft(
    client, db_session, monkeypatch
) -> None:
    owner_token, organization_id = _login(
        client, "org-owner@example.com", "pass-org-owner"
    )
    scope = _seed_report_scope(
        db_session, organization_id=organization_id, suffix="draft-review-command"
    )
    account, _ = _create_account(
        client, owner_token=owner_token, location_id=scope["location_id"]
    )
    draft_id = str(uuid.uuid4())
    brief_id = str(uuid.uuid4())
    monkeypatch.setattr(
        automation_command_service,
        "_scoped_content_draft",
        lambda *_args, **_kwargs: SimpleNamespace(
            id=draft_id,
            content_brief_id=brief_id,
            status="working",
            title="Emergency service page",
            revision=3,
        ),
    )
    rotated = client.post(
        f"/api/v1/automation/service-accounts/{account['id']}/rotate",
        headers=_headers(owner_token),
        json={
            "allowed_commands": [
                "report.retrieve",
                "content.request_draft_review",
            ]
        },
    )
    assert rotated.status_code == 200, rotated.text
    secret = rotated.json()["data"]["token"]
    body = {
        "schema_version": "insightos.automation.command.v1",
        "command_type": "content.request_draft_review",
        "organization_id": organization_id,
        "location_id": scope["location_id"],
        "correlation_id": "n8n-draft-review-1",
        "idempotency_key": "n8n-draft-review-1001",
        "reason": "Ask the owner to review the private draft",
        "target": {"campaign_id": scope["campaign_id"], "draft_id": draft_id},
    }
    response = client.post(
        "/api/v1/automation/commands", json=body, headers=_headers(secret)
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["receipt"]["status"] == "succeeded"
    assert data["receipt"]["result"]["truth"] == {
        "review_requested": True,
        "approved": False,
        "scheduled": False,
        "published": False,
        "website_changed": False,
    }
    assert data["receipt"]["result"]["draft"]["revision"] == 3
    repeated = client.post(
        "/api/v1/automation/commands", json=body, headers=_headers(secret)
    )
    assert repeated.status_code == 200
    assert repeated.json()["data"]["created"] is False

import json
import uuid
import base64
from datetime import UTC, datetime, timedelta

from app.models.audit_log import AuditLog
from app.models.organization import Organization
from app.models.user import User
from app.services.commercial_plan_service import apply_commercial_plan


def _login(client, email: str, password: str) -> tuple[dict, dict]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    payload = response.json()["data"]
    return payload["user"], {"Authorization": f"Bearer {payload['access_token']}"}


def test_enterprise_activity_is_owner_only_tenant_safe_and_payload_free(client, db_session):
    owner, owner_headers = _login(client, "org-owner@example.com", "pass-org-owner")
    organization_id = owner["organization_id"]

    blocked = client.get("/api/v1/enterprise/activity", headers=owner_headers)
    assert blocked.status_code == 403
    assert (
        blocked.json()["errors"][0]["details"]["reason_code"]
        == "organization_activity_upgrade_required"
    )

    organization = db_session.get(Organization, organization_id)
    assert organization is not None
    apply_commercial_plan(db_session, organization_id=organization_id, plan_code="enterprise")

    owner_user = db_session.query(User).filter(User.email == "org-owner@example.com").one()
    team_user = db_session.query(User).filter(User.email == "a@example.com").one()
    other_organization = (
        db_session.query(Organization).filter(Organization.id != organization_id).first()
    )
    assert other_organization is not None
    now = datetime(2026, 8, 20, 18, 0, tzinfo=UTC)
    owner_event = AuditLog(
        id=str(uuid.uuid4()),
        tenant_id=organization_id,
        actor_user_id=owner_user.id,
        event_type="enterprise.client_report_package.downloaded",
        payload_json=json.dumps(
            {
                "package_sha256": "private-package-hash",
                "storage_path": "private/customer/path.zip",
                "provider_secret": "raw-super-secret",
            }
        ),
        created_at=now,
    )
    team_event = AuditLog(
        id=str(uuid.uuid4()),
        tenant_id=organization_id,
        actor_user_id=team_user.id,
        event_type="enterprise.report_branding.updated",
        payload_json=json.dumps({"brand_name": "Private Client Name"}),
        created_at=now - timedelta(minutes=1),
    )
    system_event = AuditLog(
        id=str(uuid.uuid4()),
        tenant_id=organization_id,
        actor_user_id=None,
        event_type="automation.webhook_delivery.failed",
        payload_json=json.dumps({"endpoint_host": "private.example"}),
        created_at=now - timedelta(minutes=2),
    )
    shared_report_event = AuditLog(
        id=str(uuid.uuid4()),
        tenant_id=organization_id,
        actor_user_id=None,
        event_type="report.share_link.opened",
        payload_json=json.dumps({"token": "private-link-token"}),
        created_at=now - timedelta(minutes=3),
    )
    unknown_event = AuditLog(
        id=str(uuid.uuid4()),
        tenant_id=organization_id,
        actor_user_id=owner_user.id,
        event_type="platform.internal.secret_inspected",
        payload_json=json.dumps({"secret": "never-customer-visible"}),
        created_at=now + timedelta(minutes=1),
    )
    cross_tenant_event = AuditLog(
        id=str(uuid.uuid4()),
        tenant_id=other_organization.id,
        actor_user_id=None,
        event_type="enterprise.client_report_package.downloaded",
        payload_json=json.dumps({"organization": "other-customer"}),
        created_at=now + timedelta(minutes=2),
    )
    db_session.add_all(
        [
            owner_event,
            team_event,
            system_event,
            shared_report_event,
            unknown_event,
            cross_tenant_event,
        ]
    )
    db_session.commit()

    _, admin_headers = _login(client, "a@example.com", "pass-a")
    role_blocked = client.get("/api/v1/enterprise/activity", headers=admin_headers)
    assert role_blocked.status_code == 403

    first_page = client.get(
        "/api/v1/enterprise/activity?limit=1", headers=owner_headers
    )
    assert first_page.status_code == 200
    first_payload = first_page.json()["data"]
    assert first_payload["count"] == 1
    assert first_payload["has_more"] is True
    assert first_payload["items"][0] == {
        "kind": "client_report_package_downloaded",
        "category": "reports",
        "category_label": "Reports and exports",
        "title": "Client report package downloaded",
        "summary": "A verified package of saved location reports was downloaded.",
        "tone": "positive",
        "actor": {"label": "You", "type": "you"},
        "occurred_at": now.isoformat(),
    }
    cursor = first_payload["next_cursor"]
    assert cursor
    assert owner_event.id not in cursor
    decoded_cursor = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
    assert owner_event.id.encode() not in decoded_cursor
    assert organization_id.encode() not in decoded_cursor

    second_page = client.get(
        "/api/v1/enterprise/activity",
        params={"limit": 1, "cursor": cursor},
        headers=owner_headers,
    )
    assert second_page.status_code == 200
    second_payload = second_page.json()["data"]
    assert second_payload["items"][0]["kind"] == "report_branding_updated"
    assert second_payload["items"][0]["actor"] == {
        "label": "a@example.com",
        "type": "team_member",
    }

    wrong_filter_cursor = client.get(
        "/api/v1/enterprise/activity",
        params={"category": "reports", "cursor": cursor},
        headers=owner_headers,
    )
    assert wrong_filter_cursor.status_code == 400

    report_activity = client.get(
        "/api/v1/enterprise/activity?category=reports", headers=owner_headers
    )
    assert report_activity.status_code == 200
    report_payload = report_activity.json()["data"]
    assert {item["kind"] for item in report_payload["items"]} == {
        "client_report_package_downloaded",
        "report_branding_updated",
        "private_report_link_opened",
    }
    serialized = json.dumps(report_activity.json())
    for private_value in (
        "raw-super-secret",
        "private-package-hash",
        "private/customer/path.zip",
        "Private Client Name",
        "private-link-token",
        "other-customer",
        "enterprise.client_report_package.downloaded",
        "platform.internal.secret_inspected",
    ):
        assert private_value not in serialized
    assert report_payload["truth"] == {
        "summary": "This view shows important saved workspace actions, not every background check.",
        "raw_payloads_exposed": False,
        "internal_event_names_exposed": False,
        "internal_identifiers_exposed": False,
        "provider_diagnostics_included": False,
        "unknown_events_excluded": True,
    }
    assert set(report_payload["items"][0]) == {
        "kind",
        "category",
        "category_label",
        "title",
        "summary",
        "tone",
        "actor",
        "occurred_at",
    }

    invalid_cursor = client.get(
        "/api/v1/enterprise/activity?cursor=not-a-valid-cursor", headers=owner_headers
    )
    assert invalid_cursor.status_code == 400
    assert (
        invalid_cursor.json()["errors"][0]["details"]["reason_code"]
        == "organization_activity_cursor_invalid"
    )

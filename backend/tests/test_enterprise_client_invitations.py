import base64
import hashlib
import json
import uuid
from datetime import UTC, datetime
from io import BytesIO

from PIL import Image
from app.models.audit_log import AuditLog
from app.models.business_location import BusinessLocation
from app.models.enterprise_branding import OrganizationReportBrand
from app.models.enterprise_client_invitation import EnterpriseClientInvitation
from app.models.organization import Organization
from app.models.organization_membership import OrganizationMembership
from app.models.portfolio_targeting import (
    PortfolioLocationAccessGrant,
    PortfolioLocationGroup,
    PortfolioLocationGroupMember,
)
from app.models.user import User
from app.services.commercial_plan_service import apply_commercial_plan


MASTER_KEY_B64 = base64.b64encode(b"e" * 32).decode()


def _login(client, email: str, password: str) -> tuple[dict, dict]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    payload = response.json()["data"]
    return payload["user"], {"Authorization": f"Bearer {payload['access_token']}"}


def _enterprise_group(db_session) -> tuple[Organization, PortfolioLocationGroup]:
    owner = db_session.query(User).filter(User.email == "org-owner@example.com").one()
    membership = (
        db_session.query(OrganizationMembership)
        .filter(
            OrganizationMembership.user_id == owner.id,
            OrganizationMembership.role == "org_owner",
        )
        .one()
    )
    organization = db_session.get(Organization, membership.organization_id)
    assert organization is not None
    apply_commercial_plan(db_session, organization_id=organization.id, plan_code="enterprise")
    now = datetime.now(UTC)
    location = BusinessLocation(
        id=str(uuid.uuid4()),
        organization_id=organization.id,
        name="Client location",
        domain="client.example",
        status="active",
        created_at=now,
        updated_at=now,
    )
    group = PortfolioLocationGroup(
        id=str(uuid.uuid4()),
        tenant_id=organization.id,
        organization_id=organization.id,
        name="Client locations",
        status="active",
        version=1,
        created_at=now,
        updated_at=now,
    )
    member = PortfolioLocationGroupMember(
        id=str(uuid.uuid4()),
        tenant_id=organization.id,
        organization_id=organization.id,
        location_group_id=group.id,
        business_location_id=location.id,
        added_by_user_id=owner.id,
        created_at=now,
    )
    db_session.add_all([location, group, member])
    db_session.commit()
    return organization, group


def _save_client_brand(db_session, *, organization: Organization) -> bytes:
    owner = db_session.query(User).filter(User.email == "org-owner@example.com").one()
    output = BytesIO()
    Image.new("RGB", (96, 32), color=(47, 86, 71)).save(output, format="PNG")
    logo = output.getvalue()
    now = datetime.now(UTC)
    db_session.add(
        OrganizationReportBrand(
            tenant_id=organization.id,
            organization_id=organization.id,
            brand_name="Evergreen Search Partners",
            report_title="Evergreen client reporting",
            footer_text="Prepared for Evergreen clients.",
            accent_color="#2F5647",
            logo_content=logo,
            logo_sha256=hashlib.sha256(logo).hexdigest(),
            logo_width=96,
            logo_height=32,
            logo_updated_at=now,
            hide_platform_attribution=True,
            enabled=True,
            version=2,
            updated_by_user_id=owner.id,
            created_at=now,
            updated_at=now,
        )
    )
    db_session.commit()
    return logo


def test_owner_invites_client_once_and_can_remove_accepted_access(
    client,
    db_session,
    monkeypatch,
):
    monkeypatch.setenv("PLATFORM_MASTER_KEY", MASTER_KEY_B64)
    organization, group = _enterprise_group(db_session)
    logo = _save_client_brand(db_session, organization=organization)
    _, owner_headers = _login(client, "org-owner@example.com", "pass-org-owner")

    created = client.post(
        "/api/v1/enterprise/client-invitations",
        headers=owner_headers,
        json={
            "email": "new.client@example.com",
            "location_group_id": group.id,
            "expires_in_days": 7,
        },
    )
    assert created.status_code == 200
    payload = created.json()["data"]
    assert payload["created"] is True
    assert payload["truth"] == {
        "setup_url_shown_once": True,
        "password_shared_with_owner": False,
    }
    old_token = payload["setup_url"].rsplit("/", 1)[-1]
    invitation_id = payload["item"]["id"]

    replacement = client.post(
        "/api/v1/enterprise/client-invitations",
        headers=owner_headers,
        json={
            "email": "new.client@example.com",
            "location_group_id": group.id,
            "expires_in_days": 7,
        },
    )
    assert replacement.status_code == 200
    assert replacement.json()["data"]["created"] is False
    token = replacement.json()["data"]["setup_url"].rsplit("/", 1)[-1]
    assert token != old_token
    assert client.get(f"/api/v1/client-invitations/{old_token}").status_code == 404

    row = db_session.get(EnterpriseClientInvitation, invitation_id)
    assert row is not None
    assert row.email_hash not in {"", "new.client@example.com"}
    assert token not in row.token_hash
    assert old_token not in row.token_hash
    assert "new.client@example.com" not in row.encrypted_email
    audits = (
        db_session.query(AuditLog)
        .filter(AuditLog.tenant_id == organization.id)
        .all()
    )
    assert "new.client@example.com" not in json.dumps([audit.payload_json for audit in audits])
    assert token not in json.dumps([audit.payload_json for audit in audits])
    assert old_token not in json.dumps([audit.payload_json for audit in audits])

    listed = client.get("/api/v1/enterprise/client-invitations", headers=owner_headers)
    assert listed.status_code == 200
    listed_json = json.dumps(listed.json())
    assert "new.client@example.com" in listed_json
    assert token not in listed_json
    assert old_token not in listed_json
    assert "setup_url" not in listed_json

    preview = client.get(f"/api/v1/client-invitations/{token}")
    assert preview.status_code == 200
    assert preview.headers["cache-control"] == "private, no-store"
    assert preview.headers["referrer-policy"] == "no-referrer"
    assert preview.headers["x-content-type-options"] == "nosniff"
    assert preview.headers["x-robots-tag"] == "noindex, nofollow"
    assert preview.json()["data"] == {
        "status": "active",
        "email_hint": "n******@example.com",
        "location_group_name": "Client locations",
        "expires_at": preview.json()["data"]["expires_at"],
        "identity": {
            "display_name": "Evergreen Search Partners",
            "portal_title": "Evergreen client reporting",
            "accent_color": "#2F5647",
            "logo_data_url": f"data:image/png;base64,{base64.b64encode(logo).decode('ascii')}",
            "platform_attribution_visible": False,
        },
        "truth": {
            "summary": "This invitation creates read-only access to assigned saved reports.",
            "can_change_workspace": False,
        },
    }
    serialized_preview = json.dumps(preview.json()["data"])
    for private_field in (
        "organization_id",
        "branding_version",
        "logo_sha256",
        "logo_width",
        "logo_height",
        "storage_key",
        "footer_text",
    ):
        assert private_field not in serialized_preview

    weak_password = client.post(
        f"/api/v1/client-invitations/{token}/accept",
        json={"password": "short", "password_confirmation": "short"},
    )
    assert weak_password.status_code == 422
    assert weak_password.json()["errors"][0]["details"]["reason_code"] == "client_invitation_password_too_weak"

    accepted = client.post(
        f"/api/v1/client-invitations/{token}/accept",
        json={
            "password": "ClientPassword123",
            "password_confirmation": "ClientPassword123",
        },
    )
    assert accepted.status_code == 200
    assert accepted.headers["cache-control"] == "private, no-store"
    assert accepted.json()["data"]["user"]["org_role"] == "org_client"
    assert "access_token" not in accepted.json()["data"]
    assert "refresh_token" not in accepted.json()["data"]
    assert "lsos_access_token" in accepted.cookies
    assert "lsos_refresh_token" in accepted.cookies
    client_user = db_session.query(User).filter(User.email == "new.client@example.com").one()
    membership = (
        db_session.query(OrganizationMembership)
        .filter(
            OrganizationMembership.organization_id == organization.id,
            OrganizationMembership.user_id == client_user.id,
        )
        .one()
    )
    assert membership.role == "org_client"
    assert membership.status == "active"
    grant = (
        db_session.query(PortfolioLocationAccessGrant)
        .filter(
            PortfolioLocationAccessGrant.organization_id == organization.id,
            PortfolioLocationAccessGrant.user_id == client_user.id,
            PortfolioLocationAccessGrant.location_group_id == group.id,
        )
        .one()
    )
    assert (grant.access_role, grant.status) == ("viewer", "active")

    replay = client.post(
        f"/api/v1/client-invitations/{token}/accept",
        json={
            "password": "ClientPassword123",
            "password_confirmation": "ClientPassword123",
        },
    )
    assert replay.status_code == 410
    assert replay.json()["errors"][0]["details"]["reason_code"] == "client_invitation_accepted"

    refreshed = client.get("/api/v1/enterprise/client-invitations", headers=owner_headers)
    accepted_item = refreshed.json()["data"]["items"][0]
    assert accepted_item["status"] == "accepted"
    revoked = client.post(
        f"/api/v1/enterprise/client-invitations/{invitation_id}/revoke",
        headers=owner_headers,
        json={"expected_version": accepted_item["version"]},
    )
    assert revoked.status_code == 200
    assert revoked.json()["data"]["item"]["status"] == "revoked"
    db_session.refresh(grant)
    assert grant.status == "revoked"


def test_invitation_requires_owner_enterprise_and_current_existing_password(
    client,
    db_session,
    monkeypatch,
):
    monkeypatch.setenv("PLATFORM_MASTER_KEY", MASTER_KEY_B64)
    owner_user, owner_headers = _login(client, "org-owner@example.com", "pass-org-owner")
    organization_id = owner_user["organization_id"]
    denied = client.post(
        "/api/v1/enterprise/client-invitations",
        headers=owner_headers,
        json={
            "email": "b@example.com",
            "location_group_id": str(uuid.uuid4()),
            "expires_in_days": 7,
        },
    )
    assert denied.status_code == 403
    assert denied.json()["errors"][0]["details"]["reason_code"] == "authenticated_client_reports_upgrade_required"

    organization, group = _enterprise_group(db_session)
    assert organization.id == organization_id
    _, admin_headers = _login(client, "org-admin@example.com", "pass-org-admin")
    assert client.get("/api/v1/enterprise/client-invitations", headers=admin_headers).status_code == 403

    created = client.post(
        "/api/v1/enterprise/client-invitations",
        headers=owner_headers,
        json={
            "email": "b@example.com",
            "location_group_id": group.id,
            "expires_in_days": 3,
        },
    )
    assert created.status_code == 200
    token = created.json()["data"]["setup_url"].rsplit("/", 1)[-1]
    wrong_password = client.post(
        f"/api/v1/client-invitations/{token}/accept",
        json={"password": "WrongPassword123", "password_confirmation": "WrongPassword123"},
    )
    assert wrong_password.status_code == 409
    assert wrong_password.json()["errors"][0]["details"]["reason_code"] == "client_invitation_existing_sign_in_required"

    accepted = client.post(
        f"/api/v1/client-invitations/{token}/accept",
        json={"password": "pass-b", "password_confirmation": "pass-b"},
    )
    # Existing accounts prove possession with their current password; password strength is not redefined.
    assert accepted.status_code == 200
    assert accepted.json()["data"]["user"]["organization_id"] == organization.id


def test_invitation_acceptance_fails_closed_after_plan_downgrade(
    client,
    db_session,
    monkeypatch,
):
    monkeypatch.setenv("PLATFORM_MASTER_KEY", MASTER_KEY_B64)
    organization, group = _enterprise_group(db_session)
    _save_client_brand(db_session, organization=organization)
    _, owner_headers = _login(client, "org-owner@example.com", "pass-org-owner")
    created = client.post(
        "/api/v1/enterprise/client-invitations",
        headers=owner_headers,
        json={
            "email": "downgraded.client@example.com",
            "location_group_id": group.id,
            "expires_in_days": 7,
        },
    )
    assert created.status_code == 200
    token = created.json()["data"]["setup_url"].rsplit("/", 1)[-1]

    apply_commercial_plan(db_session, organization_id=organization.id, plan_code="solo")
    db_session.commit()
    downgraded_preview = client.get(f"/api/v1/client-invitations/{token}")
    assert downgraded_preview.status_code == 200
    assert downgraded_preview.json()["data"]["identity"] == {
        "display_name": "InsightOS",
        "portal_title": "Your private client reports",
        "accent_color": "#E85D19",
        "logo_data_url": None,
        "platform_attribution_visible": True,
    }
    denied = client.post(
        f"/api/v1/client-invitations/{token}/accept",
        json={
            "password": "DowngradePassword123",
            "password_confirmation": "DowngradePassword123",
        },
    )
    assert denied.status_code == 403
    assert denied.json()["errors"][0]["details"]["reason_code"] == "authenticated_client_reports_upgrade_required"
    assert (
        db_session.query(User).filter(User.email == "downgraded.client@example.com").first()
        is None
    )

import uuid
import base64

from app.core.settings import get_settings
from app.models.campaign import Campaign
from app.models.organization import Organization
from app.services.provider_credentials_service import upsert_provider_policy

MASTER_KEY_B64 = base64.b64encode(b"0123456789abcdef0123456789abcdef").decode("ascii")


def _set_master_key(monkeypatch) -> None:
    monkeypatch.setenv("PLATFORM_MASTER_KEY", MASTER_KEY_B64)


def _login(client, email: str, password: str) -> tuple[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    payload = response.json()["data"]
    return payload["access_token"], payload["user"]["tenant_id"]


def test_platform_owner_can_manage_provider_policy(client, db_session, monkeypatch) -> None:
    _set_master_key(monkeypatch)
    token, tenant_id = _login(client, "platform-owner@example.com", "pass-platform-owner")
    org = Organization(id=str(uuid.uuid4()), name="Org Policy API", plan_type="standard", billing_mode="subscription")
    db_session.add(org)
    db_session.commit()

    res = client.put(
        f"/api/v1/platform/organizations/{org.id}/provider-policies/dataforseo",
        json={"credential_mode": "byo_required"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["organization_id"] == org.id
    assert data["provider_name"] == "dataforseo"
    assert data["credential_mode"] == "byo_required"
    assert tenant_id == res.json()["meta"]["tenant_id"]


def test_platform_admin_cannot_modify_provider_policy(client, db_session, monkeypatch) -> None:
    _set_master_key(monkeypatch)
    token, _tenant_id = _login(client, "platform-admin@example.com", "pass-platform-admin")
    org = Organization(id=str(uuid.uuid4()), name="Org Policy Deny API", plan_type="standard", billing_mode="subscription")
    db_session.add(org)
    db_session.commit()

    res = client.put(
        f"/api/v1/platform/organizations/{org.id}/provider-policies/dataforseo",
        json={"credential_mode": "byo_required"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 403


def test_platform_admin_cannot_modify_platform_credentials(client, monkeypatch) -> None:
    _set_master_key(monkeypatch)
    token, _tenant_id = _login(client, "platform-admin@example.com", "pass-platform-admin")
    res = client.put(
        "/api/v1/platform/provider-credentials/dataforseo",
        json={"auth_mode": "api_key", "credentials": {"api_key": "x"}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 403


def test_org_roles_cannot_modify_platform_credentials(client, monkeypatch) -> None:
    _set_master_key(monkeypatch)
    token, _tenant_id = _login(client, "org-admin@example.com", "pass-org-admin")
    res = client.put(
        "/api/v1/platform/provider-credentials/dataforseo",
        json={"auth_mode": "api_key", "credentials": {"api_key": "x"}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 403


def test_platform_credentials_response_is_redacted(client, monkeypatch) -> None:
    _set_master_key(monkeypatch)
    token, _tenant_id = _login(client, "platform-owner@example.com", "pass-platform-owner")
    res = client.put(
        "/api/v1/platform/provider-credentials/dataforseo",
        json={"auth_mode": "api_key", "credentials": {"api_key": "super-secret-value"}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    payload_text = str(res.json())
    assert "super-secret-value" not in payload_text


def test_byo_required_missing_credential_returns_reason_code(client, db_session, monkeypatch) -> None:
    _set_master_key(monkeypatch)
    monkeypatch.setenv("RANK_PROVIDER_BACKEND", "serpapi")
    monkeypatch.setenv("RANK_PROVIDER_SERPAPI_API_KEY", "")
    get_settings.cache_clear()
    try:
        token, tenant_id = _login(client, "a@example.com", "pass-a")
        org = db_session.query(Organization).filter(Organization.id == tenant_id).first()
        if org is None:
            org = Organization(id=tenant_id, name="Tenant-A-Org", plan_type="standard", billing_mode="subscription")
            db_session.add(org)
        else:
            org.name = "Tenant-A-Org"
            org.plan_type = "standard"
            org.billing_mode = "subscription"
            org.status = "active"
        db_session.commit()
        upsert_provider_policy(
            db_session,
            organization_id=org.id,
            provider_name="dataforseo",
            credential_mode="byo_required",
        )
        campaign = Campaign(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            name="BYO Required Test",
            domain="example.com",
        )
        db_session.add(campaign)
        db_session.commit()

        response = client.post(
            "/api/v1/rank/schedule",
            json={"campaign_id": campaign.id, "location_code": "US"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 409
        details = response.json()["errors"][0]["details"]
        assert details["reason_code"] == "org_credential_required"
    finally:
        monkeypatch.delenv("RANK_PROVIDER_BACKEND", raising=False)
        monkeypatch.delenv("RANK_PROVIDER_SERPAPI_API_KEY", raising=False)
        get_settings.cache_clear()

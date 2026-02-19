import base64
from urllib.parse import parse_qs, urlparse

import pytest

from app.models.organization import Organization
from app.models.organization_provider_credential import OrganizationProviderCredential
from app.services.google_oauth_service import GoogleOAuthError, create_google_oauth_state, validate_google_oauth_state
from app.services.provider_credentials_service import (
    ProviderCredentialConfigurationError,
    get_organization_provider_credentials,
    resolve_provider_credentials,
    upsert_organization_provider_credentials,
    upsert_provider_policy,
)


MASTER_KEY_B64 = base64.b64encode(b"0123456789abcdef0123456789abcdef").decode("ascii")


@pytest.fixture(autouse=True)
def _oauth_env(monkeypatch) -> None:
    monkeypatch.setenv("PLATFORM_MASTER_KEY", MASTER_KEY_B64)
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "client-id")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("GOOGLE_OAUTH_REDIRECT_URI", "https://example.com/oauth/google/callback")
    monkeypatch.setenv("GOOGLE_OAUTH_AUTH_ENDPOINT", "https://accounts.google.com/o/oauth2/v2/auth")
    monkeypatch.setenv("GOOGLE_OAUTH_TOKEN_ENDPOINT", "https://oauth2.googleapis.com/token")
    monkeypatch.setenv("GOOGLE_OAUTH_SCOPE", "https://www.googleapis.com/auth/business.manage")
    monkeypatch.setenv("GOOGLE_OAUTH_STATE_TTL_SECONDS", "600")
    monkeypatch.setenv("GOOGLE_OAUTH_ACCESS_TOKEN_SKEW_SECONDS", "60")
    from app.core.settings import get_settings

    get_settings.cache_clear()


def _login(client, email: str, password: str) -> tuple[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    payload = response.json()["data"]
    return payload["access_token"], payload["user"]["tenant_id"]


def _me(client, token: str) -> dict:
    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    return response.json()["data"]


def _create_org(db_session, organization_id: str, name: str) -> None:
    db_session.add(
        Organization(
            id=organization_id,
            name=name,
            plan_type="standard",
            billing_mode="subscription",
            status="active",
        )
    )
    db_session.commit()


def test_google_oauth_start_returns_org_scoped_state(client) -> None:
    token, organization_id = _login(client, "org-admin@example.com", "pass-org-admin")
    user = _me(client, token)

    response = client.post(
        f"/api/v1/organizations/{organization_id}/providers/google/oauth/start",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["organization_id"] == organization_id
    parsed = urlparse(data["authorization_url"])
    query = parse_qs(parsed.query)
    assert query["state"][0] == data["state"]
    state_payload = validate_google_oauth_state(data["state"])
    assert state_payload["organization_id"] == organization_id
    assert state_payload["user_id"] == user["id"]


def test_google_oauth_callback_stores_encrypted_org_credentials(client, db_session, monkeypatch) -> None:
    token, organization_id = _login(client, "org-admin@example.com", "pass-org-admin")
    user = _me(client, token)
    state = create_google_oauth_state(organization_id=organization_id, user_id=user["id"])

    monkeypatch.setattr(
        "app.api.v1.google_oauth.exchange_google_authorization_code",
        lambda _code: {
            "access_token": "access-secret",
            "refresh_token": "refresh-secret",
            "expires_in": 3600,
            "expires_at": 2000000000,
            "token_type": "Bearer",
            "scope": "https://www.googleapis.com/auth/business.manage",
            "obtained_at": 1999996400,
        },
    )

    response = client.get(
        f"/api/v1/organizations/{organization_id}/providers/google/oauth/callback",
        params={"code": "oauth-code", "state": state},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["auth_mode"] == "oauth2"
    row = (
        db_session.query(OrganizationProviderCredential)
        .filter(
            OrganizationProviderCredential.organization_id == organization_id,
            OrganizationProviderCredential.provider_name == "google",
        )
        .first()
    )
    assert row is not None
    assert row.auth_mode == "oauth2"
    assert "access-secret" not in row.encrypted_secret_blob
    assert "refresh-secret" not in row.encrypted_secret_blob

    creds = get_organization_provider_credentials(db_session, organization_id, "google")
    assert creds["access_token"] == "access-secret"
    assert creds["refresh_token"] == "refresh-secret"


def test_google_oauth_callback_state_org_mismatch_returns_reason_code(client) -> None:
    token, organization_id = _login(client, "org-admin@example.com", "pass-org-admin")
    user = _me(client, token)
    wrong_org_id = "00000000-0000-0000-0000-000000000000"
    state = create_google_oauth_state(organization_id=wrong_org_id, user_id=user["id"])

    response = client.get(
        f"/api/v1/organizations/{organization_id}/providers/google/oauth/callback",
        params={"code": "oauth-code", "state": state},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400
    details = response.json()["errors"][0]["details"]
    assert details["reason_code"] == "oauth_state_org_mismatch"


def test_google_oauth_callback_exchange_failure_returns_reason_code(client, monkeypatch) -> None:
    token, organization_id = _login(client, "org-admin@example.com", "pass-org-admin")
    user = _me(client, token)
    state = create_google_oauth_state(organization_id=organization_id, user_id=user["id"])

    def _raise(_code: str) -> dict:
        raise GoogleOAuthError("Google exchange failed", reason_code="oauth_exchange_failed", status_code=502)

    monkeypatch.setattr("app.api.v1.google_oauth.exchange_google_authorization_code", _raise)

    response = client.get(
        f"/api/v1/organizations/{organization_id}/providers/google/oauth/callback",
        params={"code": "oauth-code", "state": state},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 502
    details = response.json()["errors"][0]["details"]
    assert details["reason_code"] == "oauth_exchange_failed"


def test_resolver_refreshes_expired_google_oauth_credentials(db_session, monkeypatch) -> None:
    token_payload = {
        "access_token": "old-access",
        "refresh_token": "org-refresh-token",
        "expires_in": 3600,
        "expires_at": 1,
        "token_type": "Bearer",
        "scope": "https://www.googleapis.com/auth/business.manage",
        "obtained_at": 1,
    }
    organization_id = "11111111-1111-1111-1111-111111111111"
    _create_org(db_session, organization_id, "Org Google Refresh 1")
    upsert_provider_policy(
        db_session,
        organization_id=organization_id,
        provider_name="google",
        credential_mode="byo_required",
    )
    upsert_organization_provider_credentials(
        db_session,
        organization_id=organization_id,
        provider_name="google",
        auth_mode="oauth2",
        credentials=token_payload,
    )

    monkeypatch.setattr(
        "app.services.provider_credentials_service.refresh_google_access_token",
        lambda _refresh_token: {
            "access_token": "new-access",
            "expires_in": 3600,
            "expires_at": 2000000000,
            "token_type": "Bearer",
            "scope": "https://www.googleapis.com/auth/business.manage",
            "obtained_at": 1999996400,
        },
    )

    resolved = resolve_provider_credentials(db_session, organization_id, "google")
    assert resolved["access_token"] == "new-access"
    assert resolved["refresh_token"] == "org-refresh-token"

    row = (
        db_session.query(OrganizationProviderCredential)
        .filter(
            OrganizationProviderCredential.organization_id == organization_id,
            OrganizationProviderCredential.provider_name == "google",
        )
        .first()
    )
    assert row is not None
    assert "new-access" not in row.encrypted_secret_blob


def test_resolver_requires_refresh_token_for_google_oauth(db_session) -> None:
    organization_id = "22222222-2222-2222-2222-222222222222"
    _create_org(db_session, organization_id, "Org Google Refresh 2")
    upsert_provider_policy(
        db_session,
        organization_id=organization_id,
        provider_name="google",
        credential_mode="byo_required",
    )
    upsert_organization_provider_credentials(
        db_session,
        organization_id=organization_id,
        provider_name="google",
        auth_mode="oauth2",
        credentials={
            "access_token": "old-access",
            "expires_in": 3600,
            "expires_at": 1,
            "token_type": "Bearer",
            "scope": "https://www.googleapis.com/auth/business.manage",
            "obtained_at": 1,
        },
    )
    with pytest.raises(ProviderCredentialConfigurationError) as exc_info:
        resolve_provider_credentials(db_session, organization_id, "google")
    assert exc_info.value.reason_code == "oauth_refresh_token_required"

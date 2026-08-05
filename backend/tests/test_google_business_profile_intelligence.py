from __future__ import annotations

import base64
from datetime import date

import httpx

from app.models.google_business_profile import (
    GoogleBusinessProfileDailyMetric,
    GoogleBusinessProfileSearchKeyword,
    GoogleBusinessProfileSnapshot,
)
from app.providers import google_business_profile as provider
from app.services import google_business_profile_service
from app.services.provider_credentials_service import upsert_organization_provider_credentials


def _login(client, email: str = "org-admin@example.com", password: str = "pass-org-admin") -> tuple[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    payload = response.json()["data"]
    return payload["access_token"], payload["user"]["organization_id"]


def _create_location_campaign(client, token: str, organization_id: str) -> tuple[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    location_response = client.post(
        f"/api/v1/organizations/{organization_id}/business-locations",
        headers=headers,
        json={
            "name": "Reno Junk Removal",
            "domain": "junk.example.com",
            "address_line1": "100 Main St",
            "city": "Reno",
            "region": "Nevada",
            "postal_code": "89501",
            "country_code": "US",
        },
    )
    assert location_response.status_code == 200
    location_id = location_response.json()["data"]["business_location"]["id"]
    campaign_response = client.post(
        "/api/v1/campaigns",
        headers=headers,
        json={
            "name": "Reno Junk Removal",
            "domain": "junk.example.com",
            "business_location_id": location_id,
        },
    )
    assert campaign_response.status_code == 200
    return location_id, campaign_response.json()["data"]["id"]


def _profile() -> dict:
    return {
        "name": "locations/123456789",
        "title": "Reno Junk Removal",
        "websiteUri": "https://junk.example.com/reno",
        "phoneNumbers": {"primaryPhone": "+1 775-555-0100"},
        "categories": {
            "primaryCategory": {
                "name": "categories/gcid:junk_removal_service",
                "displayName": "Junk removal service",
            }
        },
        "storefrontAddress": {
            "addressLines": ["100 Main St"],
            "locality": "Reno",
            "administrativeArea": "NV",
            "postalCode": "89501",
        },
        "regularHours": {"periods": [{"openDay": "MONDAY", "closeDay": "MONDAY"}]},
        "profile": {"description": "Local junk removal for homes and businesses."},
        "serviceItems": [{"structuredServiceItem": {"serviceTypeId": "junk-removal"}}],
        "metadata": {"hasVoiceOfMerchant": True},
        "attributes": [],
    }


def test_provider_discovers_authorized_profiles_across_accounts() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/accounts":
            return httpx.Response(
                200,
                json={
                    "accounts": [
                        {
                            "name": "accounts/44",
                            "accountName": "Top Dog Digital",
                            "role": "OWNER",
                            "permissionLevel": "OWNER_LEVEL",
                            "verificationState": "VERIFIED",
                        }
                    ]
                },
            )
        if request.url.path == "/v1/accounts/44/locations":
            return httpx.Response(200, json={"locations": [_profile()]})
        return httpx.Response(404)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        profiles = provider.discover_profiles(
            access_token="access-token",
            client=client,
        )

    assert len(profiles) == 1
    assert profiles[0]["id"] == "locations/123456789"
    assert profiles[0]["name"] == "Reno Junk Removal"
    assert profiles[0]["verified"] is True
    assert profiles[0]["primary_category"] == "Junk removal service"
    assert "Reno" in profiles[0]["address"]


def test_profile_audit_is_honest_about_unmeasured_fields(client, db_session) -> None:
    token, organization_id = _login(client)
    location_id, campaign_id = _create_location_campaign(client, token, organization_id)
    from app.models.business_location import BusinessLocation
    from app.models.campaign import Campaign

    audit = google_business_profile_service.build_profile_audit(
        profile=_profile(),
        campaign=db_session.get(Campaign, campaign_id),
        location=db_session.get(BusinessLocation, location_id),
    )

    assert audit["score"] == 100
    assert audit["needs_attention"] == 0
    photo_check = next(item for item in audit["items"] if item["field"] == "photos")
    assert photo_check["status"] == "not_measured"
    assert "does not claim" in audit["truth_note"]


def test_profile_mapping_sync_and_intelligence_are_location_scoped(
    client,
    db_session,
    monkeypatch,
) -> None:
    token, organization_id = _login(client)
    location_id, campaign_id = _create_location_campaign(client, token, organization_id)
    monkeypatch.setenv(
        "PLATFORM_MASTER_KEY",
        base64.b64encode(b"0123456789abcdef0123456789abcdef").decode("ascii"),
    )
    upsert_organization_provider_credentials(
        db_session,
        organization_id=organization_id,
        provider_name="google",
        auth_mode="oauth2",
        credentials={
            "access_token": "business-access",
            "refresh_token": "business-refresh",
            "expires_at": 4102444800,
            "expires_in": 3600,
            "scope": "https://www.googleapis.com/auth/business.manage",
        },
    )
    monkeypatch.setattr(
        google_business_profile_service.provider,
        "discover_profiles",
        lambda **_kwargs: [
            {
                "id": "locations/123456789",
                "name": "Reno Junk Removal",
                "account_id": "accounts/44",
                "account_name": "Top Dog Digital",
                "account_role": "OWNER",
                "permission_level": "OWNER_LEVEL",
                "verified": True,
                "address": "100 Main St, Reno, NV 89501",
                "website": "https://junk.example.com/reno",
                "phone": "+1 775-555-0100",
                "primary_category": "Junk removal service",
                "profile": _profile(),
            }
        ],
    )
    headers = {"Authorization": f"Bearer {token}"}
    resources = client.get(
        f"/api/v1/organizations/{organization_id}/data-connections/google-business-profile/resources",
        headers=headers,
    )
    assert resources.status_code == 200
    assert resources.json()["data"]["resources"][0]["id"] == "locations/123456789"
    assert "profile" not in resources.json()["data"]["resources"][0]

    mapped = client.put(
        f"/api/v1/organizations/{organization_id}/data-connections/google-business-profile/mappings/{campaign_id}",
        headers=headers,
        json={"external_resource_id": "locations/123456789"},
    )
    assert mapped.status_code == 200
    connection = mapped.json()["data"]["connection"]
    assert connection["business_location_id"] == location_id
    assert connection["provider_name"] == "google_business_profile"

    calls = {"profile": 0, "metrics": 0, "keywords": 0}

    def get_profile(**_kwargs):
        calls["profile"] += 1
        return _profile()

    def fetch_metrics(*, date_from: date, **_kwargs):
        calls["metrics"] += 1
        return [
            {
                "metric_name": "WEBSITE_CLICKS",
                "metric_date": date_from,
                "metric_value": 7,
                "missing_reason": None,
            },
            {
                "metric_name": "BUSINESS_IMPRESSIONS_MOBILE_MAPS",
                "metric_date": date_from,
                "metric_value": 40,
                "missing_reason": None,
            },
        ]

    def fetch_keywords(**_kwargs):
        calls["keywords"] += 1
        return [{"keyword": "junk removal reno", "impressions": 23, "measurement": "exact"}]

    monkeypatch.setattr(google_business_profile_service.provider, "get_profile", get_profile)
    monkeypatch.setattr(google_business_profile_service.provider, "fetch_daily_metrics", fetch_metrics)
    monkeypatch.setattr(google_business_profile_service.provider, "fetch_search_keywords", fetch_keywords)
    monkeypatch.setattr(google_business_profile_service, "PROFILE_SYNC_BACKFILL_DAYS", 7)

    first_sync = client.post(
        f"/api/v1/organizations/{organization_id}/data-connections/{connection['id']}/sync",
        headers=headers,
    )
    second_sync = client.post(
        f"/api/v1/organizations/{organization_id}/data-connections/{connection['id']}/sync",
        headers=headers,
    )
    assert first_sync.status_code == 200
    assert first_sync.json()["data"]["job"]["status"] == "completed"
    assert second_sync.status_code == 200
    assert second_sync.json()["data"]["job"]["idempotent_replay"] is True
    assert calls == {"profile": 1, "metrics": 1, "keywords": 3}

    intelligence = client.get(
        f"/api/v1/organizations/{organization_id}/data-connections/google-business-profile/intelligence/{campaign_id}?days=7",
        headers=headers,
    )
    assert intelligence.status_code == 200
    payload = intelligence.json()["data"]
    assert payload["data_status"] == "ready"
    assert payload["audit"]["score"] == 100
    assert payload["summary"]["website_clicks"] == 7
    assert payload["summary"]["map_appearances"] == 40
    assert payload["search_terms"][0]["keyword"] == "junk removal reno"
    assert db_session.query(GoogleBusinessProfileSnapshot).count() == 1
    assert db_session.query(GoogleBusinessProfileDailyMetric).count() == 56
    assert db_session.query(GoogleBusinessProfileSearchKeyword).count() == 3

    other_token, other_organization_id = _login(
        client,
        email="b@example.com",
        password="pass-b",
    )
    forbidden = client.get(
        f"/api/v1/organizations/{other_organization_id}/data-connections/google-business-profile/intelligence/{campaign_id}",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert forbidden.status_code == 404

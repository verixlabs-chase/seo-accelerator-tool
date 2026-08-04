from datetime import UTC, datetime

from app.models.campaign import Campaign
from app.models.business_location import BusinessLocation
from app.models.crawl import CrawlPageResult, CrawlRun, Page
from app.services import business_service_area_service


def _login(client, email: str, password: str) -> tuple[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    data = response.json()["data"]
    return data["access_token"], data["user"]["organization_id"]


def _create_location_campaign(client, token: str, org_id: str, *, name: str) -> dict:
    headers = {"Authorization": f"Bearer {token}"}
    location_response = client.post(
        f"/api/v1/organizations/{org_id}/business-locations",
        json={
            "name": name,
            "domain": "example.com",
            "city": "Reno",
            "region": "Nevada",
            "country_code": "US",
            "postal_code": "89501",
        },
        headers=headers,
    )
    assert location_response.status_code == 200
    location = location_response.json()["data"]["business_location"]
    campaign_response = client.post(
        "/api/v1/campaigns",
        json={
            "name": name,
            "domain": "example.com",
            "business_location_id": location["id"],
        },
        headers=headers,
    )
    assert campaign_response.status_code == 200
    return campaign_response.json()["data"]


def test_owner_confirms_included_and_excluded_service_areas(client) -> None:
    token, org_id = _login(client, "org-admin@example.com", "pass-org-admin")
    headers = {"Authorization": f"Bearer {token}"}
    campaign = _create_location_campaign(client, token, org_id, name="Reno Hauling")

    suggested = client.post(
        "/api/v1/business-service-areas/suggest",
        json={"campaign_id": campaign["id"]},
        headers=headers,
    )
    assert suggested.status_code == 200
    profile = suggested.json()["data"]
    assert profile["summary"]["suggested"] == 2
    reno = next(item for item in profile["items"] if item["name"] == "Reno")

    confirmed = client.patch(
        f"/api/v1/business-service-areas/{reno['id']}",
        json={"campaign_id": campaign["id"], "status": "confirmed"},
        headers=headers,
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["data"]["summary"]["confirmed_included"] == 1

    excluded = client.post(
        "/api/v1/business-service-areas",
        json={
            "campaign_id": campaign["id"],
            "area_type": "city",
            "name": "Sparks",
            "region": "Nevada",
            "relationship": "excluded",
        },
        headers=headers,
    )
    assert excluded.status_code == 200
    assert excluded.json()["data"]["summary"]["confirmed_excluded"] == 1


def test_website_area_suggestion_requires_owner_confirmation(client, db_session) -> None:
    token, org_id = _login(client, "org-owner@example.com", "pass-org-owner")
    headers = {"Authorization": f"Bearer {token}"}
    campaign_data = _create_location_campaign(client, token, org_id, name="Junk Magicians")
    campaign = db_session.get(Campaign, campaign_data["id"])
    assert campaign is not None
    now = datetime.now(UTC)
    run = CrawlRun(
        tenant_id=campaign.tenant_id,
        campaign_id=campaign.id,
        crawl_type="deep",
        status="completed",
        seed_url="https://example.com",
        created_at=now,
        started_at=now,
        finished_at=now,
    )
    db_session.add(run)
    db_session.flush()
    page = Page(
        tenant_id=campaign.tenant_id,
        campaign_id=campaign.id,
        url="https://example.com/service-areas/carson-city-nv",
        last_crawled_at=now,
        created_at=now,
    )
    db_session.add(page)
    db_session.flush()
    db_session.add(
        CrawlPageResult(
            tenant_id=campaign.tenant_id,
            campaign_id=campaign.id,
            crawl_run_id=run.id,
            page_id=page.id,
            status_code=200,
            is_indexable=1,
            title="Junk Removal in Carson City | Junk Magicians",
            crawled_at=now,
        )
    )
    db_session.commit()

    response = client.post(
        "/api/v1/business-service-areas/suggest",
        json={"campaign_id": campaign.id},
        headers=headers,
    )
    assert response.status_code == 200
    carson_city = next(
        item for item in response.json()["data"]["items"] if item["name"] == "Carson City"
    )
    assert carson_city["status"] == "suggested"
    assert carson_city["source"] == "website"


def test_service_areas_are_tenant_scoped(client) -> None:
    token_a, _org_a = _login(client, "org-admin@example.com", "pass-org-admin")
    token_b, org_b = _login(client, "b@example.com", "pass-b")
    campaign_b = _create_location_campaign(client, token_b, org_b, name="Other Market")

    response = client.get(
        f"/api/v1/business-service-areas?campaign_id={campaign_b['id']}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert response.status_code == 404


def test_nearby_communities_are_distance_checked_and_require_confirmation(
    client, db_session
) -> None:
    token, org_id = _login(client, "org-owner@example.com", "pass-org-owner")
    campaign_data = _create_location_campaign(client, token, org_id, name="Reno Service Area")
    campaign = db_session.get(Campaign, campaign_data["id"])
    assert campaign is not None
    location = db_session.get(BusinessLocation, campaign.business_location_id)
    assert location is not None
    location.latitude = 39.5296
    location.longitude = -119.8138
    db_session.commit()

    profile = business_service_area_service.suggest_nearby_communities(
        db_session,
        tenant_id=campaign.tenant_id,
        campaign_id=campaign.id,
        radius_miles=25,
        resolver=lambda _latitude, _longitude, _radius: [
            {
                "name": "Sparks",
                "region": "Nevada",
                "country_code": "US",
                "latitude": 39.5349,
                "longitude": -119.7527,
                "place_type": "city",
                "source_id": "node:1",
            },
            {
                "name": "Too Far Away",
                "region": "Nevada",
                "country_code": "US",
                "latitude": 40.5,
                "longitude": -119.8,
                "place_type": "town",
                "source_id": "node:2",
            },
        ],
    )

    assert profile["map"] == {
        "status": "ready",
        "center_latitude": 39.5296,
        "center_longitude": -119.8138,
        "radius_miles": 25.0,
        "radius_saved": True,
        "boundary_saved": False,
        "boundary_id": None,
        "boundary_points": [],
    }
    sparks = next(item for item in profile["items"] if item["name"] == "Sparks")
    assert sparks["status"] == "suggested"
    assert sparks["source"] == "map"
    assert sparks["center_latitude"] == 39.5349
    assert sparks["evidence"][0]["distance_miles"] < 4
    assert all(item["name"] != "Too Far Away" for item in profile["items"])
    assert profile["discovery"]["reviewed"] == 1

    confirmed = business_service_area_service.review_area(
        db_session,
        tenant_id=campaign.tenant_id,
        campaign_id=campaign.id,
        area_id=sparks["id"],
        next_status="confirmed",
    )
    confirmed_sparks = next(item for item in confirmed["items"] if item["id"] == sparks["id"])
    assert confirmed_sparks["status"] == "confirmed"


def test_custom_boundary_saves_owner_shape_and_keeps_only_inside_communities(
    client, db_session, monkeypatch
) -> None:
    token, org_id = _login(client, "org-owner@example.com", "pass-org-owner")
    headers = {"Authorization": f"Bearer {token}"}
    campaign_data = _create_location_campaign(client, token, org_id, name="Reno Custom Area")
    campaign = db_session.get(Campaign, campaign_data["id"])
    assert campaign is not None
    location = db_session.get(BusinessLocation, campaign.business_location_id)
    assert location is not None
    location.latitude = 39.5296
    location.longitude = -119.8138
    db_session.commit()

    points = [
        {"latitude": 39.45, "longitude": -119.9},
        {"latitude": 39.45, "longitude": -119.7},
        {"latitude": 39.6, "longitude": -119.7},
        {"latitude": 39.6, "longitude": -119.9},
    ]
    monkeypatch.setattr(
        business_service_area_service,
        "_load_boundary_communities",
        lambda _points: [
            {
                "name": "Sparks",
                "region": "Nevada",
                "country_code": "US",
                "latitude": 39.5349,
                "longitude": -119.7527,
                "place_type": "city",
                "source_id": "node:1",
            },
            {
                "name": "Carson City",
                "region": "Nevada",
                "country_code": "US",
                "latitude": 39.1638,
                "longitude": -119.7674,
                "place_type": "city",
                "source_id": "node:2",
            },
        ],
    )
    response = client.post(
        "/api/v1/business-service-areas/boundary",
        json={"campaign_id": campaign.id, "points": points},
        headers=headers,
    )
    assert response.status_code == 200
    profile = response.json()["data"]

    assert profile["map"]["boundary_saved"] is True
    assert profile["map"]["boundary_points"] == points
    assert profile["summary"]["confirmed_included"] == 1
    boundary = next(item for item in profile["items"] if item["area_type"] == "boundary")
    assert boundary["name"] == "Custom work area"
    assert boundary["status"] == "confirmed"
    sparks = next(item for item in profile["items"] if item["name"] == "Sparks")
    assert sparks["status"] == "suggested"
    assert sparks["evidence"][0]["note"] == "Inside your custom work area"
    assert all(item["name"] != "Carson City" for item in profile["items"])
    assert profile["discovery"]["reviewed"] == 1

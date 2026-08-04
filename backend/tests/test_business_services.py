from datetime import UTC, datetime

from app.models.business_service import BusinessService
from app.models.business_service_area import BusinessServiceArea
from app.models.campaign import Campaign
from app.models.crawl import CrawlPageResult, CrawlRun, Page
from app.services import keyword_research_service


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


def test_owner_can_add_and_review_location_services(client) -> None:
    token, org_id = _login(client, "org-admin@example.com", "pass-org-admin")
    headers = {"Authorization": f"Bearer {token}"}
    campaign = _create_location_campaign(client, token, org_id, name="Reno Service Shop")

    empty = client.get(
        f"/api/v1/business-services?campaign_id={campaign['id']}", headers=headers
    )
    assert empty.status_code == 200
    assert empty.json()["data"]["summary"] == {
        "confirmed": 0,
        "suggested": 0,
        "rejected": 0,
    }

    created = client.post(
        "/api/v1/business-services",
        json={"campaign_id": campaign["id"], "name": "Appliance Removal"},
        headers=headers,
    )
    assert created.status_code == 200
    item = created.json()["data"]["items"][0]
    assert item["name"] == "Appliance Removal"
    assert item["status"] == "confirmed"
    assert item["source"] == "manual"

    rejected = client.patch(
        f"/api/v1/business-services/{item['id']}",
        json={"campaign_id": campaign["id"], "status": "rejected"},
        headers=headers,
    )
    assert rejected.status_code == 200
    assert rejected.json()["data"]["summary"] == {
        "confirmed": 0,
        "suggested": 0,
        "rejected": 1,
    }


def test_website_discovery_suggests_service_pages_but_not_city_slogans(
    client,
    db_session,
) -> None:
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
    pages = [
        Page(
            tenant_id=campaign.tenant_id,
            campaign_id=campaign.id,
            url="https://example.com/services/appliance-removal",
            last_crawled_at=now,
            created_at=now,
        ),
        Page(
            tenant_id=campaign.tenant_id,
            campaign_id=campaign.id,
            url="https://example.com/about-reno",
            last_crawled_at=now,
            created_at=now,
        ),
    ]
    db_session.add_all(pages)
    db_session.flush()
    db_session.add_all(
        [
            CrawlPageResult(
                tenant_id=campaign.tenant_id,
                campaign_id=campaign.id,
                crawl_run_id=run.id,
                page_id=pages[0].id,
                status_code=200,
                is_indexable=1,
                title="Appliance Removal in Reno | Junk Magicians",
                crawled_at=now,
            ),
            CrawlPageResult(
                tenant_id=campaign.tenant_id,
                campaign_id=campaign.id,
                crawl_run_id=run.id,
                page_id=pages[1].id,
                status_code=200,
                is_indexable=1,
                title="The Biggest Little City | Junk Magicians",
                crawled_at=now,
            ),
        ]
    )
    db_session.commit()

    response = client.post(
        "/api/v1/business-services/discover",
        json={"campaign_id": campaign.id},
        headers=headers,
    )
    assert response.status_code == 200
    payload = response.json()["data"]
    names = {item["name"] for item in payload["items"]}
    assert "Appliance Removal" in names
    assert "The Biggest Little City" not in names
    assert payload["summary"]["suggested"] == 1
    assert payload["discovery"]["pages_reviewed"] == 2


def test_service_profiles_are_tenant_scoped(client) -> None:
    token_a, org_a = _login(client, "org-admin@example.com", "pass-org-admin")
    token_b, org_b = _login(client, "b@example.com", "pass-b")
    campaign_b = _create_location_campaign(client, token_b, org_b, name="Other Company")

    response = client.get(
        f"/api/v1/business-services?campaign_id={campaign_b['id']}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert response.status_code == 404
    assert org_a != org_b


def test_confirmed_service_controls_keyword_relevance() -> None:
    service = BusinessService(
        id="service-1",
        tenant_id="tenant-1",
        organization_id="tenant-1",
        business_location_id=None,
        scope_type="organization",
        scope_key="tenant-1",
        name="Junk Removal",
        normalized_name="junk removal",
        aliases=[],
        status="confirmed",
        source="manual",
        confidence=1.0,
        evidence=[],
    )
    included_area = BusinessServiceArea(
        id="area-1",
        tenant_id="tenant-1",
        organization_id="tenant-1",
        business_location_id="location-1",
        area_type="city",
        name="Reno",
        normalized_name="reno",
        region="Nevada",
        country_code="US",
        relationship="included",
        status="confirmed",
        source="manual",
        confidence=1.0,
        evidence=[],
    )
    relevant = keyword_research_service._score_candidate(
        {
            "keyword": "junk removal reno",
            "normalized_keyword": "junk removal reno",
            "source_types": {"dataforseo_ideas"},
            "tracked": False,
        },
        location=None,
        confirmed_services=[service],
        confirmed_service_areas=[included_area],
    )
    unrelated = keyword_research_service._score_candidate(
        {
            "keyword": "the biggest little city",
            "normalized_keyword": "the biggest little city",
            "source_types": {"dataforseo_ideas"},
            "tracked": False,
        },
        location=None,
        confirmed_services=[service],
        confirmed_service_areas=[included_area],
    )

    assert relevant["relevance_status"] == "relevant"
    assert relevant["matched_service_name"] == "Junk Removal"
    assert relevant["matched_service_area_name"] == "Reno"
    assert unrelated["relevance_status"] == "unrelated"
    assert unrelated["relevance_score"] == 5


def test_confirmed_exclusion_blocks_an_otherwise_relevant_search() -> None:
    service = BusinessService(
        id="service-1",
        tenant_id="tenant-1",
        organization_id="tenant-1",
        business_location_id="location-1",
        scope_type="location",
        scope_key="location-1",
        name="Junk Removal",
        normalized_name="junk removal",
        aliases=[],
        status="confirmed",
        source="manual",
        confidence=1.0,
        evidence=[],
    )
    included = BusinessServiceArea(
        id="area-reno",
        tenant_id="tenant-1",
        organization_id="tenant-1",
        business_location_id="location-1",
        area_type="city",
        name="Reno",
        normalized_name="reno",
        region="Nevada",
        country_code="US",
        relationship="included",
        status="confirmed",
        source="manual",
        confidence=1.0,
        evidence=[],
    )
    excluded = BusinessServiceArea(
        id="area-sparks",
        tenant_id="tenant-1",
        organization_id="tenant-1",
        business_location_id="location-1",
        area_type="city",
        name="Sparks",
        normalized_name="sparks",
        region="Nevada",
        country_code="US",
        relationship="excluded",
        status="confirmed",
        source="manual",
        confidence=1.0,
        evidence=[],
    )

    result = keyword_research_service._score_candidate(
        {
            "keyword": "junk removal sparks",
            "normalized_keyword": "junk removal sparks",
            "source_types": {"dataforseo_ideas"},
            "tracked": False,
        },
        location=None,
        confirmed_services=[service],
        confirmed_service_areas=[included],
        excluded_service_areas=[excluded],
    )

    assert result["relevance_status"] == "unrelated"
    assert result["matched_service_area_name"] == "Sparks"
    assert "outside your service area" in result["relevance_reason"]

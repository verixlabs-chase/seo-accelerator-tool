from datetime import date

from sqlalchemy import text

from app.models.campaign_daily_metric import CampaignDailyMetric


def _login(client, email: str = "org-admin@example.com", password: str = "pass-org-admin") -> tuple[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    payload = response.json()["data"]
    return payload["access_token"], payload["user"]["organization_id"]


def _create_subaccount(client, token: str, org_id: str, name: str) -> str:
    response = client.post(
        f"/api/v1/organizations/{org_id}/subaccounts",
        json={"name": name},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    return response.json()["data"]["subaccount"]["id"]


def test_business_location_creation_builds_internal_execution_scope(client, db_session) -> None:
    token, org_id = _login(client)
    subaccount_id = _create_subaccount(client, token, org_id, "North Region")

    created = client.post(
        f"/api/v1/organizations/{org_id}/business-locations",
        json={
            "name": "Dallas",
            "sub_account_id": subaccount_id,
            "domain": "dallas.example",
            "primary_city": "Dallas",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert created.status_code == 200
    business_location = created.json()["data"]["business_location"]
    assert business_location["sub_account_id"] == subaccount_id

    execution_scope = db_session.execute(
        text(
            """
            SELECT l.sub_account_id, l.business_location_id, l.portfolio_id, l.city
            FROM locations l
            WHERE l.business_location_id = :business_location_id
            """
        ),
        {"business_location_id": business_location["id"]},
    ).mappings().one()
    assert execution_scope["sub_account_id"] == subaccount_id
    assert execution_scope["business_location_id"] == business_location["id"]
    assert execution_scope["portfolio_id"] is not None
    assert execution_scope["city"] == "Dallas"


def test_campaign_inherits_business_location_scope_and_hierarchy_is_nested(client, db_session) -> None:
    token, org_id = _login(client)
    subaccount_id = _create_subaccount(client, token, org_id, "South Region")
    business_location_response = client.post(
        f"/api/v1/organizations/{org_id}/business-locations",
        json={
            "name": "Austin",
            "sub_account_id": subaccount_id,
            "domain": "austin.example",
            "primary_city": "Austin",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert business_location_response.status_code == 200
    business_location_id = business_location_response.json()["data"]["business_location"]["id"]

    campaign_response = client.post(
        "/api/v1/campaigns",
        json={
            "name": "Austin SEO",
            "domain": "austin.example",
            "business_location_id": business_location_id,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert campaign_response.status_code == 200
    campaign = campaign_response.json()["data"]
    assert campaign["sub_account_id"] == subaccount_id
    assert campaign["business_location_id"] == business_location_id
    assert campaign["portfolio_id"] is not None
    db_session.add(
        CampaignDailyMetric(
            organization_id=org_id,
            portfolio_id=campaign["portfolio_id"],
            sub_account_id=subaccount_id,
            campaign_id=campaign["id"],
            metric_date=date(2026, 7, 27),
            clicks=42,
            impressions=900,
            avg_position=4.8,
            sessions=65,
            conversions=7,
            technical_issue_count=3,
            intelligence_score=81.5,
            reviews_last_30d=12,
            avg_rating_last_30d=4.7,
            deterministic_hash="m" * 64,
        )
    )
    db_session.commit()

    hierarchy_response = client.get(
        f"/api/v1/organizations/{org_id}/hierarchy",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert hierarchy_response.status_code == 200
    hierarchy = hierarchy_response.json()["data"]["hierarchy"]
    assert hierarchy["totals"] == {
        "subaccounts": 1,
        "business_locations": 1,
        "execution_locations": 1,
        "campaigns": 1,
        "active_business_locations": 1,
        "unassigned_business_locations": 0,
        "integrity_issues": 0,
    }
    subaccount = hierarchy["subaccounts"][0]
    assert subaccount["id"] == subaccount_id
    location = subaccount["business_locations"][0]
    assert location["id"] == business_location_id
    assert location["execution_locations"][0]["sub_account_id"] == subaccount_id
    assert location["campaigns"][0]["id"] == campaign["id"]
    assert location["campaigns"][0]["latest_metric"]["sessions"] == 65
    assert location["performance"] == {
        "data_available": True,
        "campaigns_with_data": 1,
        "as_of": "2026-07-27",
        "clicks": 42,
        "impressions": 900,
        "avg_position": 4.8,
        "sessions": 65,
        "conversions": 7,
        "technical_issue_count": 3,
        "intelligence_score": 81.5,
        "reviews_last_30d": 12,
        "avg_rating_last_30d": 4.7,
    }


def test_campaign_rejects_business_location_subaccount_mismatch(client) -> None:
    token, org_id = _login(client)
    first_subaccount_id = _create_subaccount(client, token, org_id, "First Division")
    second_subaccount_id = _create_subaccount(client, token, org_id, "Second Division")
    location_response = client.post(
        f"/api/v1/organizations/{org_id}/business-locations",
        json={"name": "Fort Worth", "sub_account_id": first_subaccount_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    business_location_id = location_response.json()["data"]["business_location"]["id"]

    response = client.post(
        "/api/v1/campaigns",
        json={
            "name": "Mismatched Campaign",
            "domain": "mismatch.example",
            "sub_account_id": second_subaccount_id,
            "business_location_id": business_location_id,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["error"]["code"] == "business_location_subaccount_mismatch"


def test_business_location_list_and_archive_preserve_hierarchy(client) -> None:
    token, org_id = _login(client)
    subaccount_id = _create_subaccount(client, token, org_id, "Archive Division")
    created = client.post(
        f"/api/v1/organizations/{org_id}/business-locations",
        json={"name": "Houston", "sub_account_id": subaccount_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    business_location_id = created.json()["data"]["business_location"]["id"]

    listed = client.get(
        f"/api/v1/organizations/{org_id}/business-locations",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["data"]["items"]] == [business_location_id]

    archived = client.patch(
        f"/api/v1/organizations/{org_id}/business-locations/{business_location_id}",
        json={"status": "archived"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert archived.status_code == 200
    assert archived.json()["data"]["business_location"]["status"] == "archived"

    locations = client.get(
        f"/api/v1/organizations/{org_id}/locations?business_location_id={business_location_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert locations.status_code == 200
    assert locations.json()["data"]["items"][0]["status"] == "archived"

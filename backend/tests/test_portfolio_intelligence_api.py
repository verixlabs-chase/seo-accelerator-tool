from datetime import UTC, datetime

from app.models.campaign_daily_metric import CampaignDailyMetric
from app.models.data_connection import DataConnection
from app.services import data_connections_service


def _login(client, email: str = "org-admin@example.com", password: str = "pass-org-admin") -> tuple[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    payload = response.json()["data"]
    return payload["access_token"], payload["user"]["organization_id"]


def _create_location_with_campaign(
    client,
    token: str,
    org_id: str,
    *,
    subaccount_id: str,
    name: str,
) -> tuple[str, dict]:
    headers = {"Authorization": f"Bearer {token}"}
    location_response = client.post(
        f"/api/v1/organizations/{org_id}/business-locations",
        headers=headers,
        json={
            "name": name,
            "sub_account_id": subaccount_id,
            "domain": f"{name.lower()}.example.com",
            "city": name,
            "region": "Texas",
        },
    )
    assert location_response.status_code == 200
    location_id = location_response.json()["data"]["business_location"]["id"]
    campaign_response = client.post(
        "/api/v1/campaigns",
        headers=headers,
        json={
            "name": f"{name} SEO",
            "domain": f"{name.lower()}.example.com",
            "business_location_id": location_id,
        },
    )
    assert campaign_response.status_code == 200
    return location_id, campaign_response.json()["data"]


def test_portfolio_overview_ranks_locations_with_explainable_saved_evidence(client, db_session) -> None:
    token, org_id = _login(client)
    headers = {"Authorization": f"Bearer {token}"}
    subaccount_response = client.post(
        f"/api/v1/organizations/{org_id}/subaccounts",
        headers=headers,
        json={"name": "Texas Region"},
    )
    subaccount_id = subaccount_response.json()["data"]["subaccount"]["id"]
    weak_location_id, weak_campaign = _create_location_with_campaign(
        client,
        token,
        org_id,
        subaccount_id=subaccount_id,
        name="Dallas",
    )
    strong_location_id, strong_campaign = _create_location_with_campaign(
        client,
        token,
        org_id,
        subaccount_id=subaccount_id,
        name="Austin",
    )
    second_weak_location_id, second_weak_campaign = _create_location_with_campaign(
        client,
        token,
        org_id,
        subaccount_id=subaccount_id,
        name="Houston",
    )

    today = datetime.now(UTC).date()
    db_session.add_all(
        [
            CampaignDailyMetric(
                organization_id=org_id,
                portfolio_id=weak_campaign["portfolio_id"],
                sub_account_id=subaccount_id,
                campaign_id=weak_campaign["id"],
                metric_date=today,
                clicks=3,
                impressions=140,
                avg_position=24.5,
                technical_issue_count=8,
                reviews_last_30d=0,
                avg_rating_last_30d=3.8,
                deterministic_hash="w" * 64,
            ),
            CampaignDailyMetric(
                organization_id=org_id,
                portfolio_id=strong_campaign["portfolio_id"],
                sub_account_id=subaccount_id,
                campaign_id=strong_campaign["id"],
                metric_date=today,
                clicks=52,
                impressions=900,
                avg_position=4.2,
                technical_issue_count=0,
                reviews_last_30d=14,
                avg_rating_last_30d=4.8,
                deterministic_hash="s" * 64,
            ),
            CampaignDailyMetric(
                organization_id=org_id,
                portfolio_id=second_weak_campaign["portfolio_id"],
                sub_account_id=subaccount_id,
                campaign_id=second_weak_campaign["id"],
                metric_date=today,
                clicks=8,
                impressions=220,
                avg_position=18.0,
                technical_issue_count=4,
                reviews_last_30d=1,
                avg_rating_last_30d=4.1,
                deterministic_hash="h" * 64,
            ),
        ]
    )
    db_session.add_all(
        [
            DataConnection(
                tenant_id=org_id,
                organization_id=org_id,
                provider_name=provider,
                business_location_id=location_id,
                campaign_id=campaign["id"],
                external_resource_id=f"{provider}:{location_id}",
                external_resource_name=campaign["name"],
                status=data_connections_service.CONNECTION_STATUS_CURRENT,
                last_success_at=datetime.now(UTC),
            )
            for location_id, campaign in (
                (weak_location_id, weak_campaign),
                (strong_location_id, strong_campaign),
                (second_weak_location_id, second_weak_campaign),
            )
            for provider in ("google_search_console", "google_business_profile")
        ]
    )
    db_session.commit()

    response = client.get(
        f"/api/v1/organizations/{org_id}/portfolio-overview",
        headers=headers,
    )

    assert response.status_code == 200
    portfolio = response.json()["data"]["portfolio"]
    assert portfolio["summary"]["active_locations"] == 3
    assert portfolio["summary"]["locations_with_saved_performance"] == 3
    assert portfolio["top_attention"][0]["location_name"] == "Dallas"
    assert portfolio["top_attention"][0]["attention_state"] == "needs_attention"
    assert {
        reason["code"] for reason in portfolio["top_attention"][0]["reasons"]
    } >= {"website_issues", "search_position", "review_rating", "review_pace"}
    strong = next(item for item in portfolio["locations"] if item["location_name"] == "Austin")
    assert strong["attention_state"] == "on_track"
    assert strong["reasons"] == []
    assert strong["performance"]["avg_position"] == 4.2

    shared_search_issue = next(
        item for item in portfolio["shared_issues"] if item["code"] == "search_position"
    )
    assert shared_search_issue["location_count"] == 2
    assert {item["location_name"] for item in shared_search_issue["locations"]} == {
        "Dallas",
        "Houston",
    }
    assert all(item["detail"] for item in shared_search_issue["locations"])

    search_example = next(
        item
        for item in portfolio["repeatable_wins"]
        if item["code"] == "search_visibility_example"
    )
    assert search_example["source"]["location_name"] == "Austin"
    assert {item["location_name"] for item in search_example["targets"]} == {
        "Dallas",
        "Houston",
    }
    assert "not proof" in search_example["guardrail"]


def test_portfolio_overview_blocks_cross_organization_access(client) -> None:
    token, org_id = _login(client)
    other_token, other_org_id = _login(client, "b@example.com", "pass-b")
    assert org_id != other_org_id

    response = client.get(
        f"/api/v1/organizations/{org_id}/portfolio-overview",
        headers={"Authorization": f"Bearer {other_token}"},
    )

    assert response.status_code == 403

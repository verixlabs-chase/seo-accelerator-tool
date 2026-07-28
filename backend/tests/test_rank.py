from app.models.organization import Organization
from app.models.user import User
from tests.helpers.economic_setup import provision_test_organization


def _login(client, email, password):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["data"]["access_token"]



def test_rank_keyword_schedule_snapshots_and_trends(client, db_session):
    token = _login(client, "a@example.com", "pass-a")
    user = db_session.query(User).filter(User.email == "a@example.com").first()
    assert user is not None
    organization = db_session.query(Organization).filter(Organization.id == user.tenant_id).first()
    assert organization is not None
    provision_test_organization(db_session, organization)

    campaign = client.post(
        "/api/v1/campaigns",
        json={"name": "Rank Campaign", "domain": "rank.com"},
        headers={"Authorization": f"Bearer {token}"},
    ).json()["data"]

    add = client.post(
        "/api/v1/rank/keywords",
        json={
            "campaign_id": campaign["id"],
            "cluster_name": "Primary Services",
            "keyword": "best local seo agency",
            "location_code": "US",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert add.status_code == 200

    schedule = client.post(
        "/api/v1/rank/schedule",
        json={"campaign_id": campaign["id"], "location_code": "US"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert schedule.status_code == 200
    assert schedule.json()["data"]["snapshots_created"] >= 1
    assert schedule.json()["data"]["truth"]["classification"] in {"synthetic", "in_progress"}

    snapshots = client.get(
        f"/api/v1/rank/snapshots?campaign_id={campaign['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert snapshots.status_code == 200
    assert len(snapshots.json()["data"]["items"]) >= 1
    assert snapshots.json()["data"]["truth"]["classification"] == "synthetic"

    trends = client.get(
        f"/api/v1/rank/trends?campaign_id={campaign['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert trends.status_code == 200
    assert len(trends.json()["data"]["items"]) >= 1
    assert trends.json()["data"]["tracked_keywords"] == 1
    assert trends.json()["data"]["truth"]["classification"] == "synthetic"


def test_bulk_keyword_onboarding_and_portfolio_summary(client, db_session):
    token = _login(client, "a@example.com", "pass-a")
    user = db_session.query(User).filter(User.email == "a@example.com").first()
    assert user is not None
    organization = db_session.query(Organization).filter(Organization.id == user.tenant_id).first()
    assert organization is not None
    provision_test_organization(db_session, organization)

    campaign = client.post(
        "/api/v1/campaigns",
        json={"name": "Reno Rank Campaign", "domain": "reno.example"},
        headers={"Authorization": f"Bearer {token}"},
    ).json()["data"]

    bulk = client.post(
        "/api/v1/rank/keywords/bulk",
        json={
            "campaign_id": campaign["id"],
            "cluster_name": "Junk removal",
            "keywords": ["junk removal reno", "appliance removal", "JUNK REMOVAL RENO"],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert bulk.status_code == 200
    assert bulk.json()["data"]["created_count"] == 2
    assert bulk.json()["data"]["location_code"] == "United States"

    keywords = client.get(
        f"/api/v1/rank/keywords?campaign_id={campaign['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert keywords.status_code == 200
    keyword_items = keywords.json()["data"]["items"]
    assert len(keyword_items) == 2
    assert {item["cluster"] for item in keyword_items} == {"Junk removal"}

    portfolio = client.get(
        "/api/v1/rank/portfolio",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert portfolio.status_code == 200
    portfolio_data = portfolio.json()["data"]
    assert portfolio_data["summary"]["tracked_keywords"] == 2
    assert portfolio_data["items"][0]["location_name"] == "Reno Rank Campaign"

    deleted = client.delete(
        f"/api/v1/rank/keywords/{keyword_items[0]['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert deleted.status_code == 200
    assert deleted.json()["data"]["deleted"] is True

def _login(client, email, password):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


def test_rank_keyword_schedule_snapshots_and_trends(client):
    token = _login(client, "a@example.com", "pass-a")
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

    snapshots = client.get(
        f"/api/v1/rank/snapshots?campaign_id={campaign['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert snapshots.status_code == 200
    assert len(snapshots.json()["data"]["items"]) >= 1

    trends = client.get(
        f"/api/v1/rank/trends?campaign_id={campaign['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert trends.status_code == 200
    assert len(trends.json()["data"]["items"]) >= 1


def _login(client, email, password):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


def test_competitor_crud_snapshots_and_gaps(client):
    token = _login(client, "a@example.com", "pass-a")
    campaign = client.post(
        "/api/v1/campaigns",
        json={"name": "Competitor Campaign", "domain": "ownsite.com"},
        headers={"Authorization": f"Bearer {token}"},
    ).json()["data"]

    create = client.post(
        "/api/v1/competitors",
        json={
            "campaign_id": campaign["id"],
            "domain": "rival.com",
            "label": "Rival One",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert create.status_code == 200

    listed = client.get(
        f"/api/v1/competitors?campaign_id={campaign['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert listed.status_code == 200
    assert len(listed.json()["data"]["items"]) == 1

    snapshots = client.get(
        f"/api/v1/competitors/snapshots?campaign_id={campaign['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert snapshots.status_code == 200
    assert snapshots.json()["data"]["summary"]["snapshots_collected"] == 1
    assert len(snapshots.json()["data"]["items"]) >= 1

    gaps = client.get(
        f"/api/v1/competitors/gaps?campaign_id={campaign['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert gaps.status_code == 200
    assert len(gaps.json()["data"]["items"]) >= 1


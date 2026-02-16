def _login(client, email, password):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


def test_content_asset_lifecycle_and_internal_links(client):
    token = _login(client, "a@example.com", "pass-a")
    campaign = client.post(
        "/api/v1/campaigns",
        json={"name": "Content Campaign", "domain": "content.com"},
        headers={"Authorization": f"Bearer {token}"},
    ).json()["data"]

    a1 = client.post(
        "/api/v1/content/assets",
        json={
            "campaign_id": campaign["id"],
            "cluster_name": "Local SEO",
            "title": "Local SEO Starter Guide",
            "planned_month": 1,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert a1.status_code == 200
    asset1_id = a1.json()["data"]["id"]

    a2 = client.post(
        "/api/v1/content/assets",
        json={
            "campaign_id": campaign["id"],
            "cluster_name": "Technical SEO",
            "title": "Technical SEO Audit Checklist",
            "planned_month": 1,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert a2.status_code == 200
    asset2_id = a2.json()["data"]["id"]

    bad_transition = client.patch(
        f"/api/v1/content/assets/{asset1_id}",
        json={"status": "published"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert bad_transition.status_code == 400

    for asset_id, url in [(asset1_id, "https://content.com/local-seo-guide"), (asset2_id, "https://content.com/tech-seo-checklist")]:
        assert client.patch(
            f"/api/v1/content/assets/{asset_id}",
            json={"status": "draft"},
            headers={"Authorization": f"Bearer {token}"},
        ).status_code == 200
        assert client.patch(
            f"/api/v1/content/assets/{asset_id}",
            json={"status": "approved"},
            headers={"Authorization": f"Bearer {token}"},
        ).status_code == 200
        published = client.patch(
            f"/api/v1/content/assets/{asset_id}",
            json={"status": "published", "target_url": url},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert published.status_code == 200
        assert published.json()["data"]["status"] == "published"

    plan = client.get(
        f"/api/v1/content/plan?campaign_id={campaign['id']}&month_number=1",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert plan.status_code == 200
    assert len(plan.json()["data"]["items"]) >= 2

    links = client.get(
        f"/api/v1/internal-links/recommendations?campaign_id={campaign['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert links.status_code == 200
    assert len(links.json()["data"]["items"]) >= 2


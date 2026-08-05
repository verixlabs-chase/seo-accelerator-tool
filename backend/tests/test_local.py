from sqlalchemy import text

from app.services import location_normalization_service


def _login(client, email, password):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


def test_local_health_and_reviews_velocity(client):
    token = _login(client, "a@example.com", "pass-a")
    campaign = client.post(
        "/api/v1/campaigns",
        json={"name": "Local Campaign", "domain": "local.com"},
        headers={"Authorization": f"Bearer {token}"},
    ).json()["data"]

    health = client.get(
        f"/api/v1/local/health?campaign_id={campaign['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert health.status_code == 200
    assert "health_score" in health.json()["data"]
    assert health.json()["data"]["truth"]["classification"] in {"synthetic", "in_progress"}

    map_pack = client.get(
        f"/api/v1/local/map-pack?campaign_id={campaign['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert map_pack.status_code == 200
    assert "map_pack_position" in map_pack.json()["data"]
    assert map_pack.json()["data"]["truth"]["classification"] == "synthetic"

    reviews = client.get(
        f"/api/v1/reviews?campaign_id={campaign['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert reviews.status_code == 200
    assert len(reviews.json()["data"]["items"]) >= 1
    assert reviews.json()["data"]["truth"]["classification"] in {"synthetic", "in_progress"}

    velocity = client.get(
        f"/api/v1/reviews/velocity?campaign_id={campaign['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert velocity.status_code == 200
    assert "reviews_last_30d" in velocity.json()["data"]
    assert "avg_rating_last_30d" in velocity.json()["data"]
    assert velocity.json()["data"]["truth"]["classification"] in {"synthetic", "in_progress"}


def test_location_context_resolves_and_caches_map_and_provider_metadata(
    client,
    db_session,
    monkeypatch,
):
    token = _login(client, "org-admin@example.com", "pass-org-admin")
    me = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    ).json()["data"]
    org_id = me["organization_id"]
    subaccount = client.post(
        f"/api/v1/organizations/{org_id}/subaccounts",
        json={"name": "Western Region"},
        headers={"Authorization": f"Bearer {token}"},
    ).json()["data"]["subaccount"]
    business_location = client.post(
        f"/api/v1/organizations/{org_id}/business-locations",
        json={
            "name": "Reno",
            "sub_account_id": subaccount["id"],
            "domain": "reno.example",
            "city": "Reno",
            "region": "NV",
            "country_code": "US",
        },
        headers={"Authorization": f"Bearer {token}"},
    ).json()["data"]["business_location"]
    campaign = client.post(
        "/api/v1/campaigns",
        json={
            "name": "Reno SEO",
            "domain": "reno.example",
            "business_location_id": business_location["id"],
        },
        headers={"Authorization": f"Bearer {token}"},
    ).json()["data"]

    before = client.get(
        f"/api/v1/local/location-context?campaign_id={campaign['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert before.status_code == 200
    assert before.json()["data"]["base_map"]["status"] == "setup_required"
    assert before.json()["data"]["map_rank_coverage"] == {
        "status": "setup_required",
        "coverage_type": "paid_geo_grid",
        "is_paid": True,
        "message": "Finish the map and search-area setup before running area-by-area checks.",
    }

    monkeypatch.setattr(
        location_normalization_service,
        "_resolve_coordinates",
        lambda _location: {
            "status": "resolved",
            "message": "resolved",
            "latitude": 39.5296,
            "longitude": -119.8138,
            "precision": "city_center",
        },
    )
    monkeypatch.setattr(
        location_normalization_service,
        "_resolve_dataforseo_location",
        lambda _db, *, organization_id, location: {
            "status": "resolved",
            "message": "resolved",
            "location_code": "1022653",
            "location_name": "Reno, Nevada, United States",
            "location_type": "City",
        },
    )
    resolved = client.post(
        f"/api/v1/local/location-context/resolve?campaign_id={campaign['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resolved.status_code == 200
    payload = resolved.json()["data"]
    assert payload["base_map"]["status"] == "ready"
    assert payload["coordinates"]["precision"] == "city_center"
    assert payload["provider_location"]["status"] == "ready"
    assert payload["provider_location"]["name"] == "Reno, Nevada, United States"
    assert payload["provider_location"]["code"] == "1022653"
    assert payload["map_rank_coverage"]["status"] == "available"
    assert "separate reference" in payload["map_rank_coverage"]["message"]

    execution_location = db_session.execute(
        text(
            """
            SELECT region, city, lat, lng
            FROM locations
            WHERE business_location_id = :business_location_id
            """
        ),
        {"business_location_id": business_location["id"]},
    ).mappings().one()
    assert execution_location["region"] == "NV"
    assert execution_location["city"] == "Reno"
    assert float(execution_location["lat"]) == 39.5296
    assert float(execution_location["lng"]) == -119.8138


def test_location_context_does_not_cross_tenant_scope(client):
    token_a = _login(client, "a@example.com", "pass-a")
    token_b = _login(client, "b@example.com", "pass-b")
    campaign_b = client.post(
        "/api/v1/campaigns",
        json={"name": "Other tenant", "domain": "other.example"},
        headers={"Authorization": f"Bearer {token_b}"},
    ).json()["data"]

    response = client.get(
        f"/api/v1/local/location-context?campaign_id={campaign_b['id']}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert response.status_code == 404
    assert response.json()["errors"][0]["details"]["reason_code"] == "campaign_not_found"

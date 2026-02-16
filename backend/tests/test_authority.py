def _login(client, email, password):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


def test_authority_and_citation_endpoints(client):
    token = _login(client, "a@example.com", "pass-a")
    campaign = client.post(
        "/api/v1/campaigns",
        json={"name": "Authority Campaign", "domain": "authority.com"},
        headers={"Authorization": f"Bearer {token}"},
    ).json()["data"]

    outreach = client.post(
        "/api/v1/authority/outreach-campaigns",
        json={"campaign_id": campaign["id"], "name": "Month 3 Outreach"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert outreach.status_code == 200
    outreach_id = outreach.json()["data"]["id"]

    contact = client.post(
        "/api/v1/authority/contacts",
        json={
            "campaign_id": campaign["id"],
            "outreach_campaign_id": outreach_id,
            "full_name": "Alex Partner",
            "email": "alex@example.com",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert contact.status_code == 200

    backlinks = client.get(
        f"/api/v1/authority/backlinks?campaign_id={campaign['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert backlinks.status_code == 200
    assert len(backlinks.json()["data"]["items"]) >= 1

    citation_submit = client.post(
        "/api/v1/citations/submissions",
        json={"campaign_id": campaign["id"], "directory_name": "Yelp"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert citation_submit.status_code == 200

    citation_status = client.get(
        f"/api/v1/citations/status?campaign_id={campaign['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert citation_status.status_code == 200
    assert len(citation_status.json()["data"]["items"]) >= 1


def _login(client, email, password):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


def _login_with_org(client, email, password):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    payload = response.json()["data"]
    return payload["access_token"], payload["user"]["organization_id"]


def test_campaigns_are_tenant_isolated(client):
    token_a = _login(client, "a@example.com", "pass-a")
    token_b = _login(client, "b@example.com", "pass-b")

    create_a = client.post(
        "/api/v1/campaigns",
        json={"name": "A Campaign", "domain": "a.com"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert create_a.status_code == 200

    create_b = client.post(
        "/api/v1/campaigns",
        json={"name": "B Campaign", "domain": "b.com"},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert create_b.status_code == 200

    list_a = client.get("/api/v1/campaigns", headers={"Authorization": f"Bearer {token_a}"})
    list_b = client.get("/api/v1/campaigns", headers={"Authorization": f"Bearer {token_b}"})
    assert len(list_a.json()["data"]["items"]) == 1
    assert len(list_b.json()["data"]["items"]) == 1
    assert list_a.json()["data"]["items"][0]["domain"] == "a.com"
    assert list_b.json()["data"]["items"][0]["domain"] == "b.com"


def test_campaign_create_persists_sub_account_id_when_valid(client):
    token, org_id = _login_with_org(client, "org-admin@example.com", "pass-org-admin")
    subaccount = client.post(
        f"/api/v1/organizations/{org_id}/subaccounts",
        json={"name": "Campaign Ops"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert subaccount.status_code == 200
    sub_account_id = subaccount.json()["data"]["subaccount"]["id"]

    created = client.post(
        "/api/v1/campaigns",
        json={"name": "Scoped Campaign", "domain": "scoped.example", "sub_account_id": sub_account_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert created.status_code == 200
    payload = created.json()["data"]
    assert payload["sub_account_id"] == sub_account_id


def test_campaign_create_rejects_sub_account_from_different_org(client):
    token_a, _org_a = _login_with_org(client, "org-admin@example.com", "pass-org-admin")
    token_b, org_b = _login_with_org(client, "b@example.com", "pass-b")
    subaccount_b = client.post(
        f"/api/v1/organizations/{org_b}/subaccounts",
        json={"name": "OrgB Ops"},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert subaccount_b.status_code == 200
    foreign_sub_account_id = subaccount_b.json()["data"]["subaccount"]["id"]

    created = client.post(
        "/api/v1/campaigns",
        json={"name": "Illegal Scope", "domain": "illegal.example", "sub_account_id": foreign_sub_account_id},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert created.status_code == 200
    assert created.json()["error"]["code"] == "subaccount_not_found"


def test_campaign_create_rejects_inactive_sub_account(client):
    token, org_id = _login_with_org(client, "org-owner@example.com", "pass-org-owner")
    subaccount = client.post(
        f"/api/v1/organizations/{org_id}/subaccounts",
        json={"name": "Inactive Ops"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert subaccount.status_code == 200
    sub_account_id = subaccount.json()["data"]["subaccount"]["id"]
    archived = client.patch(
        f"/api/v1/subaccounts/{sub_account_id}",
        json={"status": "archived"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert archived.status_code == 200

    created = client.post(
        "/api/v1/campaigns",
        json={"name": "Inactive Scope", "domain": "inactive.example", "sub_account_id": sub_account_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert created.status_code == 200
    assert created.json()["error"]["code"] == "subaccount_inactive"

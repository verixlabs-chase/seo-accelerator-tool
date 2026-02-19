def _login(client, email: str, password: str) -> tuple[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    payload = response.json()["data"]
    return payload["access_token"], payload["user"]["tenant_id"]


def test_org_isolation_blocks_cross_org_subaccount_access(client) -> None:
    token_a, _org_a = _login(client, "org-admin@example.com", "pass-org-admin")
    _token_b, org_b = _login(client, "b@example.com", "pass-b")

    response = client.get(
        f"/api/v1/organizations/{org_b}/subaccounts",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert response.status_code == 403
    details = response.json()["errors"][0]["details"]
    assert details["reason_code"] == "organization_scope_mismatch"


def test_subaccount_name_unique_within_organization(client) -> None:
    token, org_id = _login(client, "org-admin@example.com", "pass-org-admin")
    first = client.post(
        f"/api/v1/organizations/{org_id}/subaccounts",
        json={"name": "Ops Alpha"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert first.status_code == 200

    second = client.post(
        f"/api/v1/organizations/{org_id}/subaccounts",
        json={"name": "Ops Alpha"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert second.status_code == 409
    details = second.json()["errors"][0]["details"]
    assert details["reason_code"] == "subaccount_name_conflict"


def test_subaccount_soft_delete_sets_archived_status(client) -> None:
    token, org_id = _login(client, "org-owner@example.com", "pass-org-owner")
    created = client.post(
        f"/api/v1/organizations/{org_id}/subaccounts",
        json={"name": "Ops Beta"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert created.status_code == 200
    sub_id = created.json()["data"]["subaccount"]["id"]

    patched = client.patch(
        f"/api/v1/subaccounts/{sub_id}",
        json={"status": "archived"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert patched.status_code == 200
    assert patched.json()["data"]["subaccount"]["status"] == "archived"

    listed = client.get(
        f"/api/v1/organizations/{org_id}/subaccounts",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert listed.status_code == 200
    item = next(row for row in listed.json()["data"]["items"] if row["id"] == sub_id)
    assert item["status"] == "archived"


def test_patch_cross_org_subaccount_returns_not_found(client) -> None:
    token_b, org_b = _login(client, "b@example.com", "pass-b")
    created = client.post(
        f"/api/v1/organizations/{org_b}/subaccounts",
        json={"name": "OrgB Ops"},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert created.status_code == 200
    sub_id = created.json()["data"]["subaccount"]["id"]

    token_a, _org_a = _login(client, "org-admin@example.com", "pass-org-admin")
    patched = client.patch(
        f"/api/v1/subaccounts/{sub_id}",
        json={"name": "Illegal Rename"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert patched.status_code == 404

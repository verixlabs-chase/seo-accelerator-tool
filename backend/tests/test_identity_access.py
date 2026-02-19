import uuid
from datetime import UTC, datetime

from app.core.passwords import hash_password
from app.models.campaign import Campaign
from app.models.crawl import CrawlRun
from app.models.organization import Organization
from app.models.organization_membership import OrganizationMembership
from app.models.user import User


def _login(client, email: str, password: str, organization_id: str | None = None) -> dict:
    payload = {"email": email, "password": password}
    if organization_id is not None:
        payload["organization_id"] = organization_id
    response = client.post("/api/v1/auth/login", json=payload)
    return {"status_code": response.status_code, "json": response.json()}


def test_login_success_and_failure(client) -> None:
    good = _login(client, "a@example.com", "pass-a")
    assert good["status_code"] == 200
    assert good["json"]["data"]["access_token"]

    bad = _login(client, "a@example.com", "wrong-pass")
    assert bad["status_code"] == 401


def test_token_tampering_is_rejected(client) -> None:
    login = _login(client, "a@example.com", "pass-a")
    token = login["json"]["data"]["access_token"]
    assert token
    tampered = f"{token}x"
    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {tampered}"})
    assert response.status_code == 401


def test_cross_org_access_denied(client, db_session) -> None:
    login_a = _login(client, "a@example.com", "pass-a")
    assert login_a["status_code"] == 200
    token_a = login_a["json"]["data"]["access_token"]

    login_b = _login(client, "b@example.com", "pass-b")
    assert login_b["status_code"] == 200
    org_b_id = login_b["json"]["data"]["user"]["organization_id"]

    campaign_b = Campaign(id=str(uuid.uuid4()), tenant_id=org_b_id, name="Cross Org Campaign", domain="crossorg.com")
    db_session.add(campaign_b)
    run_b = CrawlRun(
        id=str(uuid.uuid4()),
        tenant_id=org_b_id,
        campaign_id=campaign_b.id,
        crawl_type="deep",
        status="running",
        seed_url="https://crossorg.com",
    )
    db_session.add(run_b)
    db_session.commit()

    response = client.get(
        f"/api/v1/crawl/run-progress?crawl_run_id={run_b.id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert response.status_code in {403, 404}


def test_platform_and_org_route_access_control(client, db_session) -> None:
    org_user_login = _login(client, "org-admin@example.com", "pass-org-admin")
    assert org_user_login["status_code"] == 200
    org_user_token = org_user_login["json"]["data"]["access_token"]

    platform_list_denied = client.get("/api/v1/platform/orgs", headers={"Authorization": f"Bearer {org_user_token}"})
    assert platform_list_denied.status_code == 403

    platform_only_user = User(
        id=str(uuid.uuid4()),
        tenant_id=str(uuid.uuid4()),
        email="platform-only@example.com",
        hashed_password=hash_password("pass-platform-only"),
        is_platform_user=True,
        platform_role="platform_admin",
        is_active=True,
        created_at=datetime.now(UTC),
    )
    db_session.add(platform_only_user)
    db_session.commit()

    platform_login = _login(client, "platform-only@example.com", "pass-platform-only")
    assert platform_login["status_code"] == 200
    platform_token = platform_login["json"]["data"]["access_token"]
    assert platform_login["json"]["data"]["user"]["organization_id"] is None

    org_route_denied = client.get("/api/v1/campaigns", headers={"Authorization": f"Bearer {platform_token}"})
    assert org_route_denied.status_code == 403

    platform_route_allowed = client.get("/api/v1/platform/orgs", headers={"Authorization": f"Bearer {platform_token}"})
    assert platform_route_allowed.status_code == 200


def test_multi_org_requires_selection_endpoint(client, db_session) -> None:
    login = _login(client, "a@example.com", "pass-a")
    assert login["status_code"] == 200
    user_id = login["json"]["data"]["user"]["id"]
    org_id = login["json"]["data"]["user"]["organization_id"]
    assert org_id is not None

    second_org = Organization(
        id=str(uuid.uuid4()),
        name=f"second-org-{uuid.uuid4().hex[:6]}",
        plan_type="standard",
        billing_mode="subscription",
        status="active",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db_session.add(second_org)
    db_session.flush()
    db_session.add(
        OrganizationMembership(
            id=str(uuid.uuid4()),
            user_id=user_id,
            organization_id=second_org.id,
            role="org_user",
            status="active",
            created_at=datetime.now(UTC),
        )
    )
    db_session.commit()

    multi = _login(client, "a@example.com", "pass-a")
    assert multi["status_code"] == 200
    data = multi["json"]["data"]
    assert data["requires_org_selection"] is True
    assert data["access_token"] is None
    refresh_token = data["refresh_token"]
    assert refresh_token
    assert len(data["organizations"]) >= 2

    select_res = client.post(
        "/api/v1/auth/select-org",
        json={"refresh_token": refresh_token, "organization_id": second_org.id},
    )
    assert select_res.status_code == 200
    selected = select_res.json()["data"]
    assert selected["access_token"]
    assert selected["user"]["organization_id"] == second_org.id

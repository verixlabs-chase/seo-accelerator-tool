from datetime import UTC, datetime
import uuid

from sqlalchemy import text

import app.services.business_location_service as business_location_service


def _login(client, email: str, password: str) -> tuple[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    payload = response.json()["data"]
    return payload["access_token"], payload["user"]["tenant_id"]


def test_business_location_create_auto_creates_internal_portfolio(client, db_session) -> None:
    token, org_id = _login(client, "org-admin@example.com", "pass-org-admin")

    response = client.post(
        f"/api/v1/organizations/{org_id}/business-locations",
        json={"name": "Main Street", "domain": "example.com", "primary_city": "Austin"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert "portfolio" not in payload
    business_location = payload["business_location"]
    assert business_location["organization_id"] == org_id
    assert business_location["name"] == "Main Street"
    assert business_location["domain"] == "example.com"
    assert business_location["primary_city"] == "Austin"

    portfolio = db_session.execute(
        text(
            """
            SELECT organization_id, business_location_id, name, code, status, timezone, default_sla_tier
            FROM portfolios
            WHERE business_location_id = :business_location_id
            """
        ),
        {"business_location_id": business_location["id"]},
    ).mappings().one()
    assert portfolio["organization_id"] == org_id
    assert portfolio["business_location_id"] == business_location["id"]
    assert portfolio["status"] == "active"
    assert portfolio["timezone"] == "UTC"
    assert portfolio["default_sla_tier"] == "standard"
    assert portfolio["name"].startswith("Internal Portfolio - ")
    assert portfolio["code"].startswith("bl-")


def test_business_location_create_respects_org_scope(client) -> None:
    token_a, _org_a = _login(client, "org-admin@example.com", "pass-org-admin")
    _token_b, org_b = _login(client, "b@example.com", "pass-b")

    response = client.post(
        f"/api/v1/organizations/{org_b}/business-locations",
        json={"name": "Cross Org"},
        headers={"Authorization": f"Bearer {token_a}"},
    )

    assert response.status_code == 403
    details = response.json()["errors"][0]["details"]
    assert details["reason_code"] == "organization_scope_mismatch"


def test_business_location_conflict_does_not_create_extra_portfolio(client, db_session) -> None:
    token, org_id = _login(client, "org-owner@example.com", "pass-org-owner")

    first = client.post(
        f"/api/v1/organizations/{org_id}/business-locations",
        json={"name": "Duplicate Name"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert first.status_code == 200

    second = client.post(
        f"/api/v1/organizations/{org_id}/business-locations",
        json={"name": "Duplicate Name"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert second.status_code == 409
    assert second.json()["errors"][0]["details"]["reason_code"] == "business_location_conflict"

    business_location_count = db_session.execute(
        text(
            """
            SELECT count(*)
            FROM business_locations
            WHERE organization_id = :organization_id
              AND name = :name
            """
        ),
        {"organization_id": org_id, "name": "Duplicate Name"},
    ).scalar_one()
    portfolio_count = db_session.execute(
        text(
            """
            SELECT count(*)
            FROM portfolios
            WHERE organization_id = :organization_id
              AND business_location_id IN (
                  SELECT id
                  FROM business_locations
                  WHERE organization_id = :organization_id
                    AND name = :name
              )
            """
        ),
        {"organization_id": org_id, "name": "Duplicate Name"},
    ).scalar_one()

    assert business_location_count == 1
    assert portfolio_count == 1


def test_business_location_rolls_back_when_portfolio_auto_create_fails(client, db_session, monkeypatch) -> None:
    token, org_id = _login(client, "org-admin@example.com", "pass-org-admin")
    existing_portfolio_id = str(uuid.uuid4())
    conflict_code = "bl-conflict"
    now = datetime.now(UTC)

    db_session.execute(
        text(
            """
            INSERT INTO portfolios (
                id,
                organization_id,
                name,
                code,
                status,
                timezone,
                default_sla_tier,
                archived_at,
                created_at,
                updated_at,
                business_location_id
            ) VALUES (
                :id,
                :organization_id,
                :name,
                :code,
                :status,
                :timezone,
                :default_sla_tier,
                :archived_at,
                :created_at,
                :updated_at,
                :business_location_id
            )
            """
        ),
        {
            "id": existing_portfolio_id,
            "organization_id": org_id,
            "name": "Existing Internal Portfolio",
            "code": conflict_code,
            "status": "active",
            "timezone": "UTC",
            "default_sla_tier": "standard",
            "archived_at": None,
            "created_at": now,
            "updated_at": now,
            "business_location_id": None,
        },
    )
    db_session.commit()

    monkeypatch.setattr(business_location_service, "_build_internal_portfolio_code", lambda _business_location_id: conflict_code)

    response = client.post(
        f"/api/v1/organizations/{org_id}/business-locations",
        json={"name": "Rollback Check"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 409
    assert response.json()["errors"][0]["details"]["reason_code"] == "portfolio_auto_create_conflict"

    business_location_count = db_session.execute(
        text(
            """
            SELECT count(*)
            FROM business_locations
            WHERE organization_id = :organization_id
              AND name = :name
            """
        ),
        {"organization_id": org_id, "name": "Rollback Check"},
    ).scalar_one()
    assert business_location_count == 0
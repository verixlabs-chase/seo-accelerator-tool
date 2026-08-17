from datetime import UTC, datetime
import uuid

from sqlalchemy import text

import app.services.business_location_service as business_location_service
from app.models.business_location import BusinessLocation
from app.models.commercial_feature_activation import CommercialFeatureActivation
from app.models.portfolio import Portfolio
from app.services.commercial_plan_service import apply_commercial_plan


def _login(client, email: str, password: str) -> tuple[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    payload = response.json()["data"]
    return payload["access_token"], payload["user"]["organization_id"]


def test_business_location_create_auto_creates_internal_portfolio(client, db_session) -> None:
    token, org_id = _login(client, "org-admin@example.com", "pass-org-admin")

    response = client.post(
        f"/api/v1/organizations/{org_id}/business-locations",
        json={
            "name": "Main Street",
            "domain": "example.com",
            "primary_city": "Austin",
            "city": "Austin",
            "region": "Texas",
            "country_code": "US",
            "latitude": 30.2672,
            "longitude": -97.7431,
        },
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
    assert business_location["city"] == "Austin"
    assert business_location["region"] == "Texas"
    assert business_location["country_code"] == "US"
    assert business_location["latitude"] == 30.2672
    assert business_location["longitude"] == -97.7431
    assert business_location["coordinate_precision"] == "manual"

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
    # This test exercises uniqueness after one active location already exists,
    # so give it a real plan with another available slot.
    apply_commercial_plan(db_session, organization_id=org_id, plan_code="multi_location")
    db_session.commit()

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


def test_business_location_rejects_whitespace_name(client, db_session) -> None:
    token, org_id = _login(client, "org-admin@example.com", "pass-org-admin")

    response = client.post(
        f"/api/v1/organizations/{org_id}/business-locations",
        json={"name": "   "},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422

    business_location_count = db_session.execute(
        text(
            """
            SELECT count(*)
            FROM business_locations
            WHERE organization_id = :organization_id
            """
        ),
        {"organization_id": org_id},
    ).scalar_one()
    portfolio_count = db_session.execute(
        text(
            """
            SELECT count(*)
            FROM portfolios
            WHERE organization_id = :organization_id
              AND business_location_id IS NOT NULL
            """
        ),
        {"organization_id": org_id},
    ).scalar_one()

    assert business_location_count == 0
    assert portfolio_count == 0


def test_solo_location_allowance_denial_is_atomic_and_customer_safe(client, db_session) -> None:
    token, org_id = _login(client, "org-admin@example.com", "pass-org-admin")
    apply_commercial_plan(db_session, organization_id=org_id, plan_code="solo")
    db_session.commit()
    headers = {"Authorization": f"Bearer {token}"}

    first = client.post(
        f"/api/v1/organizations/{org_id}/business-locations",
        json={"name": "Solo covered location"},
        headers=headers,
    )
    denied = client.post(
        f"/api/v1/organizations/{org_id}/business-locations",
        json={"name": "Solo overage location"},
        headers=headers,
    )

    assert first.status_code == 200
    assert denied.status_code == 409
    details = denied.json()["errors"][0]["details"]
    assert details == {
        "message": (
            "Your Solo plan includes 1 active location. Archive another location or "
            "choose a plan with more locations before turning this one on."
        ),
        "reason_code": "active_location_allowance_exhausted",
        "plan_code": "solo",
        "plan_name": "Solo",
        "included_locations": 1,
        "active_locations": 1,
        "remaining_locations": 0,
        "over_limit_by": 0,
        "required_plan_code": "multi_location",
        "required_plan_name": "Growth",
    }
    assert (
        db_session.query(BusinessLocation)
        .filter(BusinessLocation.organization_id == org_id)
        .count()
        == 1
    )
    assert (
        db_session.query(Portfolio)
        .filter(
            Portfolio.organization_id == org_id,
            Portfolio.business_location_id.is_not(None),
        )
        .count()
        == 1
    )


def test_archive_releases_solo_slot_and_reactivation_rechecks_capacity(
    client, db_session
) -> None:
    token, org_id = _login(client, "org-owner@example.com", "pass-org-owner")
    apply_commercial_plan(db_session, organization_id=org_id, plan_code="solo")
    db_session.commit()
    headers = {"Authorization": f"Bearer {token}"}

    first = client.post(
        f"/api/v1/organizations/{org_id}/business-locations",
        json={"name": "First solo location"},
        headers=headers,
    ).json()["data"]["business_location"]
    archived = client.patch(
        f"/api/v1/organizations/{org_id}/business-locations/{first['id']}",
        json={"status": "archived"},
        headers=headers,
    )
    second = client.post(
        f"/api/v1/organizations/{org_id}/business-locations",
        json={"name": "Second solo location"},
        headers=headers,
    ).json()["data"]["business_location"]
    denied = client.patch(
        f"/api/v1/organizations/{org_id}/business-locations/{first['id']}",
        json={"status": "active"},
        headers=headers,
    )

    assert archived.status_code == 200
    assert denied.status_code == 409
    assert denied.json()["errors"][0]["details"]["reason_code"] == (
        "active_location_allowance_exhausted"
    )
    db_session.expire_all()
    assert db_session.get(BusinessLocation, first["id"]).status == "archived"
    assert db_session.get(BusinessLocation, second["id"]).status == "active"

    assert (
        client.patch(
            f"/api/v1/organizations/{org_id}/business-locations/{second['id']}",
            json={"status": "archived"},
            headers=headers,
        ).status_code
        == 200
    )
    reactivated = client.patch(
        f"/api/v1/organizations/{org_id}/business-locations/{first['id']}",
        json={"status": "active"},
        headers=headers,
    )
    assert reactivated.status_code == 200
    assert reactivated.json()["data"]["business_location"]["status"] == "active"


def test_growth_to_solo_downgrade_preserves_locations_and_reports_overage(
    client, db_session
) -> None:
    token, org_id = _login(client, "org-admin@example.com", "pass-org-admin")
    apply_commercial_plan(db_session, organization_id=org_id, plan_code="multi_location")
    db_session.commit()
    headers = {"Authorization": f"Bearer {token}"}
    created_ids = []
    for name in ("Preserved north shop", "Preserved south shop"):
        response = client.post(
            f"/api/v1/organizations/{org_id}/business-locations",
            json={"name": name},
            headers=headers,
        )
        assert response.status_code == 200
        created_ids.append(response.json()["data"]["business_location"]["id"])

    apply_commercial_plan(db_session, organization_id=org_id, plan_code="solo")
    db_session.commit()
    summary = client.get("/api/v1/usage/credits", headers=headers)

    assert summary.status_code == 200
    plan = summary.json()["data"]["plan"]
    assert plan["code"] == "solo"
    assert plan["included_locations"] == 1
    assert plan["active_locations"] == 2
    assert plan["remaining_locations"] == 0
    assert plan["over_limit_by"] == 1
    assert plan["can_activate_location"] is False
    assert "tier_version" not in plan
    assert "allowance_source" not in plan
    db_session.expire_all()
    assert {
        db_session.get(BusinessLocation, location_id).status for location_id in created_ids
    } == {"active"}
    assert (
        db_session.query(Portfolio)
        .filter(Portfolio.business_location_id.in_(created_ids))
        .count()
        == 2
    )


def test_observe_bridge_reports_overage_but_does_not_block_location_changes(
    client, db_session
) -> None:
    token, org_id = _login(client, "org-admin@example.com", "pass-org-admin")
    activation = db_session.get(
        CommercialFeatureActivation,
        "active_location_allowance",
    )
    assert activation is not None
    activation.state = "observe"
    apply_commercial_plan(db_session, organization_id=org_id, plan_code="solo")
    db_session.commit()
    headers = {"Authorization": f"Bearer {token}"}

    first = client.post(
        f"/api/v1/organizations/{org_id}/business-locations",
        json={"name": "Observed first location"},
        headers=headers,
    )
    second = client.post(
        f"/api/v1/organizations/{org_id}/business-locations",
        json={"name": "Observed overage location"},
        headers=headers,
    )
    assert first.status_code == 200
    assert second.status_code == 200
    first_id = first.json()["data"]["business_location"]["id"]

    assert (
        client.patch(
            f"/api/v1/organizations/{org_id}/business-locations/{first_id}",
            json={"status": "archived"},
            headers=headers,
        ).status_code
        == 200
    )
    assert (
        client.patch(
            f"/api/v1/organizations/{org_id}/business-locations/{first_id}",
            json={"status": "active"},
            headers=headers,
        ).status_code
        == 200
    )

    plan = client.get("/api/v1/usage/credits", headers=headers).json()["data"]["plan"]
    assert plan["included_locations"] == 1
    assert plan["active_locations"] == 2
    assert plan["over_limit_by"] == 1
    assert plan["location_allowance_enforced"] is False
    assert plan["can_activate_location"] is True

    activation = db_session.get(
        CommercialFeatureActivation,
        "active_location_allowance",
    )
    activation.state = "enforced"
    db_session.commit()
    denied = client.post(
        f"/api/v1/organizations/{org_id}/business-locations",
        json={"name": "Blocked after activation"},
        headers=headers,
    )
    assert denied.status_code == 409
    assert denied.json()["errors"][0]["details"]["reason_code"] == (
        "active_location_allowance_exhausted"
    )

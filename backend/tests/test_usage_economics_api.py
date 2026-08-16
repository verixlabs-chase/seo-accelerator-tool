from app.models.organization import Organization
from app.models.cost_economics import CostLedgerEntry
from app.models.audit_log import AuditLog
from app.core.config import get_settings
from app.services import rank_service
from app.services.commercial_plan_service import apply_commercial_plan
from tests.helpers.economic_setup import provision_test_organization


def _login(client, email: str, password: str) -> tuple[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    payload = response.json()["data"]
    return payload["access_token"], payload["user"]["tenant_id"]


def test_customer_allowance_uses_credits_and_hides_internal_money(client, db_session) -> None:
    token, tenant_id = _login(client, "org-admin@example.com", "pass-org-admin")
    org = db_session.get(Organization, tenant_id)
    assert org is not None
    apply_commercial_plan(db_session, organization_id=org.id, plan_code="solo")
    db_session.commit()

    response = client.get(
        "/api/v1/usage/credits",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["plan"]["name"] == "Solo"
    assert data["plan"]["monthly_price"] == 299.0
    assert data["plan"]["included_locations"] == 1
    assert data["commercial_catalog_version"] == "commercial-plans-2026-08-v2"
    assert data["plan"]["over_limit_by"] == 0
    assert data["plan"]["can_activate_location"] is True
    assert "tier_version" not in data["plan"]
    assert "allowance_source" not in data["plan"]
    assert data["upgrade"]["plan_name"] == "Growth"
    assert data["upgrade"]["monthly_price"] == 699.0
    wordpress = next(
        item for item in data["capabilities"] if item["code"] == "wordpress_execution"
    )
    assert wordpress["available"] is False
    assert wordpress["required_plan"] == "Growth"
    performance_trend = next(
        item for item in data["capabilities"] if item["code"] == "performance_trend"
    )
    owner_report = next(
        item for item in data["capabilities"] if item["code"] == "campaign_report"
    )
    deeper_plan = next(
        item for item in data["capabilities"] if item["code"] == "campaign_strategy"
    )
    profile_fleet = next(
        item
        for item in data["capabilities"]
        if item["code"] == "business_profile_fleet_actions"
    )
    automatic_review_replies = next(
        item
        for item in data["capabilities"]
        if item["code"] == "automatic_review_replies"
    )
    assert performance_trend["available"] is True
    assert performance_trend["required_plan"] == "Solo"
    assert owner_report["available"] is True
    assert owner_report["required_plan"] == "Solo"
    assert deeper_plan["available"] is False
    assert deeper_plan["required_plan"] == "Growth"
    assert profile_fleet["available"] is False
    assert profile_fleet["required_plan"] == "Growth"
    assert automatic_review_replies["available"] is False
    assert automatic_review_replies["required_plan"] == "Growth"
    assert data["credits"]["monthly"] == 1495
    assert data["credits"]["remaining"] == 1495
    assert data["credits"]["name"] == "Insight Credits"
    assert data["catalog_version"] == "insight-credits-2026-08-v1"
    assert {item["code"] for item in data["action_prices"]} >= {
        "keyword_research_refresh",
        "competitor_discovery",
        "authority_inventory_refresh",
        "ranking_check",
        "keyword_relevance_review",
    }
    research_price = next(
        item for item in data["action_prices"] if item["code"] == "keyword_research_refresh"
    )
    assert "up to three saved competitor domains" in research_price["result"]
    serialized = str(data).lower()
    assert "currency" not in serialized
    assert "monthly_revenue" not in serialized
    assert "api_budget" not in serialized
    assert "provider_reported_cost" not in serialized
    assert "gross_margin_percent" not in data
    assert "revenue" not in data


def test_platform_margin_view_and_versioned_allocation(client, db_session) -> None:
    token, tenant_id = _login(client, "platform-owner@example.com", "pass-platform-owner")
    org = db_session.get(Organization, tenant_id)
    assert org is not None
    org.plan_type = "enterprise"
    db_session.commit()

    allocation_response = client.post(
        f"/api/v1/platform/orgs/{org.id}/cost-allocations",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "month": "2026-07",
            "hosting_cost": "20.00",
            "storage_cost": "5.00",
            "email_cost": "2.00",
            "support_cost": "30.00",
            "other_cost": "3.00",
            "source": "july-close",
        },
    )
    assert allocation_response.status_code == 200
    allocation_data = allocation_response.json()["data"]
    assert allocation_data["allocation"]["version"] == 1
    assert allocation_data["margin"]["total_cogs"] == 60.0

    margin_response = client.get(
        f"/api/v1/platform/orgs/{org.id}/margin?month=2026-07",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert margin_response.status_code == 200
    margin = margin_response.json()["data"]
    assert margin["revenue"] == 1999.0
    assert margin["allocation_status"] == "configured"
    assert margin["modeled_heavy_use"]["publishable"] is True
    assert (
        db_session.query(AuditLog)
        .filter(
            AuditLog.tenant_id == org.id,
            AuditLog.event_type == "platform.org.cost_allocation.created",
        )
        .count()
        == 1
    )


def test_platform_admin_cannot_write_cost_allocations(client, db_session) -> None:
    token, tenant_id = _login(client, "platform-admin@example.com", "pass-platform-admin")
    response = client.post(
        f"/api/v1/platform/orgs/{tenant_id}/cost-allocations",
        headers={"Authorization": f"Bearer {token}"},
        json={"month": "2026-07"},
    )
    assert response.status_code == 403


def test_rank_schedule_reserves_then_reconciles_dataforseo_cost(
    client,
    db_session,
    monkeypatch,
) -> None:
    class _RankProvider:
        def collect_keyword_snapshot(self, **_kwargs):
            return {
                "position": 8,
                "confidence": 0.95,
                "provider_reported_cost": 0.019,
                "cost_currency": "USD",
            }

    monkeypatch.setenv("RANK_PROVIDER_BACKEND", "dataforseo")
    get_settings.cache_clear()
    monkeypatch.setattr(
        rank_service,
        "get_rank_provider_for_organization",
        lambda *_args, **_kwargs: _RankProvider(),
    )
    monkeypatch.setattr(
        rank_service,
        "resolve_provider_credential_owner",
        lambda *_args, **_kwargs: "platform",
    )
    try:
        token, tenant_id = _login(client, "a@example.com", "pass-a")
        org = db_session.get(Organization, tenant_id)
        assert org is not None
        provision_test_organization(db_session, org)

        location = client.post(
            f"/api/v1/organizations/{org.id}/business-locations",
            json={"name": "Metered Rank Location"},
            headers={"Authorization": f"Bearer {token}"},
        ).json()["data"]["business_location"]

        campaign = client.post(
            "/api/v1/campaigns",
            json={
                "name": "Metered Rank Campaign",
                "domain": "metered.example",
                "business_location_id": location["id"],
            },
            headers={"Authorization": f"Bearer {token}"},
        ).json()["data"]
        keyword = client.post(
            "/api/v1/rank/keywords",
            json={
                "campaign_id": campaign["id"],
                "cluster_name": "Primary",
                "keyword": "junk removal reno",
                "location_code": "US",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert keyword.status_code == 200

        scheduled = client.post(
            "/api/v1/rank/schedule",
            json={"campaign_id": campaign["id"], "location_code": "US"},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert scheduled.status_code == 200
        rows = (
            db_session.query(CostLedgerEntry)
            .filter(
                CostLedgerEntry.organization_id == org.id,
                CostLedgerEntry.campaign_id == campaign["id"],
            )
            .order_by(CostLedgerEntry.created_at.asc())
            .all()
        )
        assert [row.event_type for row in rows] == ["reservation", "reconciliation"]
        assert float(rows[0].estimated_cost) == 0.02
        assert float(rows[1].provider_reported_cost) == 0.019
    finally:
        monkeypatch.delenv("RANK_PROVIDER_BACKEND", raising=False)
        get_settings.cache_clear()

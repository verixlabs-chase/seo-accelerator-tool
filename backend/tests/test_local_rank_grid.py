from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from app.models.business_location import BusinessLocation
from app.models.cost_economics import CostLedgerEntry
from app.models.local_rank_grid import LocalRankGridPoint
from app.models.organization import Organization
from app.models.rank import CampaignKeyword, KeywordCluster
from app.services import local_rank_grid_service
from tests.conftest import create_test_campaign


def _location_campaign(db_session, organization, *, name: str, city: str):
    campaign = create_test_campaign(
        db_session,
        organization.id,
        tenant_id=organization.id,
        name=name,
        domain=f"{name.lower().replace(' ', '-')}.example",
    )
    location = BusinessLocation(
        organization_id=organization.id,
        name=name,
        domain=campaign.domain,
        city=city,
        region="NV",
        country_code="US",
        latitude=39.5296,
        longitude=-119.8138,
        provider_location_code="1022653",
        provider_location_name=f"{city},Nevada,United States",
        provider_location_type="City",
        status="active",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db_session.add(location)
    db_session.flush()
    campaign.business_location_id = location.id
    campaign.setup_state = "Active"
    cluster = KeywordCluster(
        tenant_id=organization.id,
        campaign_id=campaign.id,
        name="Local services",
    )
    db_session.add(cluster)
    db_session.flush()
    keywords = [
        CampaignKeyword(
            tenant_id=organization.id,
            campaign_id=campaign.id,
            cluster_id=cluster.id,
            keyword=phrase,
            location_code="1022653",
        )
        for phrase in ("junk removal near me", "furniture removal")
    ]
    db_session.add_all(keywords)
    db_session.commit()
    return campaign, location, keywords


def test_preview_counts_checks_and_credits_without_exposing_provider(
    db_session, create_test_org, monkeypatch
) -> None:
    organization = create_test_org(name="Rank grid preview org")
    campaign, location, keywords = _location_campaign(
        db_session, organization, name="Reno Haulers", city="Reno"
    )
    monkeypatch.setattr(local_rank_grid_service, "_credential_owner", lambda *_args: "platform")

    preview = local_rank_grid_service.preview_run(
        db_session,
        tenant_id=organization.id,
        organization_id=organization.id,
        campaign_id=campaign.id,
        keyword_ids=[row.id for row in keywords],
        grid_size=5,
        radius_miles=5,
    )

    assert preview["business_location_id"] == location.id
    assert preview["points_per_phrase"] == 25
    assert preview["total_checks"] == 50
    assert preview["estimated_credits"] == 3
    assert preview["source_label"] == "Google Maps results"
    assert "provider" not in preview


def test_run_is_idempotent_location_scoped_and_persists_every_point(
    db_session, create_test_org, monkeypatch
) -> None:
    organization = create_test_org(name="Rank grid durable org")
    campaign, location, keywords = _location_campaign(
        db_session, organization, name="Reno Cleanup", city="Reno"
    )
    monkeypatch.setattr(local_rank_grid_service, "_credential_owner", lambda *_args: "platform")

    run, created = local_rank_grid_service.create_run(
        db_session,
        tenant_id=organization.id,
        organization_id=organization.id,
        created_by_user_id=None,
        campaign_id=campaign.id,
        keyword_ids=[row.id for row in keywords],
        grid_size=5,
        radius_miles=5,
        idempotency_key="same-grid-request-001",
    )
    replay, replay_created = local_rank_grid_service.create_run(
        db_session,
        tenant_id=organization.id,
        organization_id=organization.id,
        created_by_user_id=None,
        campaign_id=campaign.id,
        keyword_ids=[row.id for row in keywords],
        grid_size=5,
        radius_miles=5,
        idempotency_key="same-grid-request-001",
    )

    assert created is True
    assert replay_created is False
    assert replay.id == run.id
    assert run.business_location_id == location.id
    points = db_session.query(LocalRankGridPoint).filter(LocalRankGridPoint.run_id == run.id).all()
    assert len(points) == 50
    assert {(row.row_index, row.column_index) for row in points} == {
        (row, column) for row in range(5) for column in range(5)
    }

    result = local_rank_grid_service.dispatch_run(
        db_session, run_id=run.id, tenant_id=organization.id
    )
    db_session.refresh(run)
    assert result["submitted"] == 50
    assert run.status == "completed"
    assert run.completed_checks == 50
    assert all(point.status in {"ranked", "not_found"} for point in points)


def test_failed_tasks_are_not_charged_and_reserved_credits_return(
    db_session, create_test_org, monkeypatch
) -> None:
    organization = create_test_org(name="Rank grid failure org")
    campaign, _location, keywords = _location_campaign(
        db_session, organization, name="Failure Cleanup", city="Reno"
    )
    monkeypatch.setattr(local_rank_grid_service, "_credential_owner", lambda *_args: "platform")
    run, _created = local_rank_grid_service.create_run(
        db_session,
        tenant_id=organization.id,
        organization_id=organization.id,
        created_by_user_id=None,
        campaign_id=campaign.id,
        keyword_ids=[keywords[0].id],
        grid_size=3,
        radius_miles=2,
        idempotency_key="failed-grid-request-001",
    )

    class FailedProvider:
        def submit(self, requests):
            return [
                {
                    "point_id": item.point_id,
                    "task_id": None,
                    "status": "failed",
                    "status_code": 50000,
                    "status_message": "not completed",
                    "cost": Decimal("0"),
                }
                for item in requests
            ]

    monkeypatch.setattr(local_rank_grid_service, "_provider_for_run", lambda *_args: FailedProvider())
    local_rank_grid_service.dispatch_run(db_session, run_id=run.id, tenant_id=organization.id)
    db_session.refresh(run)

    assert run.status == "failed"
    assert run.failed_checks == 9
    assert Decimal(run.provider_reported_cost or 0) == Decimal("0")
    release = (
        db_session.query(CostLedgerEntry)
        .filter(
            CostLedgerEntry.reservation_id == run.reservation_id,
            CostLedgerEntry.event_type == "release",
        )
        .one()
    )
    assert release.customer_credit_units == -1


def test_rank_grid_api_requires_confirmation_contract_and_returns_location_run(
    client, db_session, monkeypatch
) -> None:
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "org-admin@example.com", "password": "pass-org-admin"},
    )
    token = login.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    organization_id = client.get("/api/v1/auth/me", headers=headers).json()["data"][
        "organization_id"
    ]
    organization = db_session.get(Organization, organization_id)
    campaign, location, keywords = _location_campaign(
        db_session, organization, name="API Grid Cleanup", city="Reno"
    )
    monkeypatch.setattr(local_rank_grid_service, "_credential_owner", lambda *_args: "platform")

    preview = client.post(
        "/api/v1/local/rank-grid/preview",
        headers=headers,
        json={
            "campaign_id": campaign.id,
            "keyword_ids": [row.id for row in keywords],
            "grid_size": 5,
            "radius_miles": 5,
        },
    )
    assert preview.status_code == 200
    assert preview.json()["data"]["total_checks"] == 50

    create_payload = {
        "campaign_id": campaign.id,
        "keyword_ids": [row.id for row in keywords],
        "grid_size": 5,
        "radius_miles": 5,
        "idempotency_key": "api-confirmed-grid-001",
    }
    created = client.post(
        "/api/v1/local/rank-grid/runs",
        headers=headers,
        json=create_payload,
    )
    assert created.status_code == 202
    run = created.json()["data"]["run"]
    assert run["business_location_id"] == location.id
    assert run["status"] == "completed"
    assert run["completed_checks"] == 50
    assert len(run["points"]) == 50

    replayed = client.post(
        "/api/v1/local/rank-grid/runs",
        headers=headers,
        json=create_payload,
    )
    assert replayed.status_code == 202
    assert replayed.json()["data"]["created"] is False
    assert replayed.json()["data"]["run"]["id"] == run["id"]
    assert replayed.json()["data"]["run"]["status"] == "completed"

    history = client.get(
        f"/api/v1/local/rank-grid/runs?campaign_id={campaign.id}", headers=headers
    )
    assert history.status_code == 200
    assert history.json()["data"]["items"][0]["id"] == run["id"]

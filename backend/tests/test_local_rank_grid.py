from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from app.models.business_location import BusinessLocation
from app.models.commercial_feature_activation import CommercialFeatureActivation
from app.models.competitor import Competitor
from app.models.cost_economics import CostLedgerEntry
from app.models.local_rank_grid import LocalRankGridCompetitorPoint, LocalRankGridPoint
from app.models.organization import Organization
from app.models.rank import CampaignKeyword, KeywordCluster
from app.services import local_rank_grid_service
from app.services.commercial_plan_service import apply_commercial_plan
from app.services.cost_economics_service import get_customer_credit_summary
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
    assert run.metric_contract_id == "local_grid.position"
    assert run.metric_contract_version == "1.0"
    assert run.grid_definition_hash != "legacy"
    assert all(point.scope_key != "legacy" for point in points)
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


def test_queued_grid_is_released_without_provider_call_after_downgrade(
    db_session, create_test_org, monkeypatch
) -> None:
    organization = create_test_org(name="Rank grid downgrade guard org")
    apply_commercial_plan(
        db_session, organization_id=organization.id, plan_code="multi_location"
    )
    campaign, location, keywords = _location_campaign(
        db_session, organization, name="Covered Grid Shop", city="Reno"
    )
    db_session.add(
        BusinessLocation(
            organization_id=organization.id,
            name="Second grid shop",
            status="active",
        )
    )
    db_session.commit()
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
        idempotency_key="grid-before-downgrade",
    )
    apply_commercial_plan(db_session, organization_id=organization.id, plan_code="solo")
    db_session.commit()
    provider_constructions: list[str] = []
    monkeypatch.setattr(
        local_rank_grid_service,
        "_provider_for_run",
        lambda *_args: provider_constructions.append("called"),
    )

    result = local_rank_grid_service.dispatch_run(
        db_session, run_id=run.id, tenant_id=organization.id
    )

    assert provider_constructions == []
    assert result == {"run_id": run.id, "submitted": 0, "status": "failed"}
    db_session.refresh(run)
    assert run.error_code == "active_location_overage_blocks_provider_work"
    assert run.failed_checks == 9
    assert (
        db_session.query(CostLedgerEntry)
        .filter(
            CostLedgerEntry.reservation_id == run.reservation_id,
            CostLedgerEntry.event_type == "release",
        )
        .count()
        == 1
    )
    assert db_session.get(BusinessLocation, location.id).status == "active"


def test_observe_queued_grid_is_stopped_and_released_after_activation(
    db_session, create_test_org, monkeypatch
) -> None:
    organization = create_test_org(name="Observed rank grid activation org")
    activation = db_session.get(
        CommercialFeatureActivation,
        "active_location_allowance",
    )
    assert activation is not None
    activation.state = "observe"
    campaign, _location, keywords = _location_campaign(
        db_session, organization, name="Observed Grid Shop", city="Reno"
    )
    db_session.add(
        BusinessLocation(
            organization_id=organization.id,
            name="Observed grid overage shop",
            status="active",
        )
    )
    db_session.commit()
    monkeypatch.setattr(
        local_rank_grid_service,
        "_credential_owner",
        lambda *_args: "platform",
    )
    run, _created = local_rank_grid_service.create_run(
        db_session,
        tenant_id=organization.id,
        organization_id=organization.id,
        created_by_user_id=None,
        campaign_id=campaign.id,
        keyword_ids=[keywords[0].id],
        grid_size=3,
        radius_miles=2,
        idempotency_key="grid-observe-before-activation",
    )

    activation = db_session.get(
        CommercialFeatureActivation,
        "active_location_allowance",
    )
    activation.state = "enforced"
    db_session.commit()
    provider_constructions: list[str] = []
    monkeypatch.setattr(
        local_rank_grid_service,
        "_provider_for_run",
        lambda *_args: provider_constructions.append("called"),
    )

    result = local_rank_grid_service.dispatch_run(
        db_session, run_id=run.id, tenant_id=organization.id
    )

    assert provider_constructions == []
    assert result == {"run_id": run.id, "submitted": 0, "status": "failed"}
    db_session.refresh(run)
    assert run.error_code == "active_location_overage_blocks_provider_work"
    assert (
        db_session.query(CostLedgerEntry)
        .filter(
            CostLedgerEntry.reservation_id == run.reservation_id,
            CostLedgerEntry.event_type == "release",
        )
        .count()
        == 1
    )
    assert get_customer_credit_summary(
        db_session, organization_id=organization.id
    )["credits"]["reserved"] == 0


def test_queued_grid_rejects_archived_target_before_provider_construction(
    db_session, create_test_org, monkeypatch
) -> None:
    organization = create_test_org(name="Rank grid archived target org")
    campaign, location, keywords = _location_campaign(
        db_session, organization, name="Archive Grid Shop", city="Reno"
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
        idempotency_key="grid-before-archive",
    )
    location.status = "archived"
    db_session.commit()
    provider_constructions: list[str] = []
    monkeypatch.setattr(
        local_rank_grid_service,
        "_provider_for_run",
        lambda *_args: provider_constructions.append("called"),
    )

    result = local_rank_grid_service.dispatch_run(
        db_session, run_id=run.id, tenant_id=organization.id
    )

    assert provider_constructions == []
    assert result["submitted"] == 0
    db_session.refresh(run)
    assert run.error_code == "active_business_location_required_for_provider_work"
    assert (
        db_session.query(CostLedgerEntry)
        .filter(
            CostLedgerEntry.reservation_id == run.reservation_id,
            CostLedgerEntry.event_type == "release",
        )
        .count()
        == 1
    )
    assert get_customer_credit_summary(
        db_session, organization_id=organization.id
    )["credits"]["reserved"] == 0


def test_mid_batch_downgrade_stops_new_provider_calls_and_reconciles_terminal_work(
    db_session, create_test_org, monkeypatch
) -> None:
    organization = create_test_org(name="Rank grid mid-batch downgrade org")
    apply_commercial_plan(
        db_session, organization_id=organization.id, plan_code="multi_location"
    )
    campaign, _location, keywords = _location_campaign(
        db_session, organization, name="Mid Batch Grid Shop", city="Reno"
    )
    third_keyword = CampaignKeyword(
        tenant_id=organization.id,
        campaign_id=campaign.id,
        cluster_id=keywords[0].cluster_id,
        keyword="estate cleanout",
        location_code="1022653",
    )
    db_session.add_all(
        [
            third_keyword,
            BusinessLocation(
                organization_id=organization.id,
                name="Second mid-batch shop",
                status="active",
            ),
        ]
    )
    db_session.commit()
    monkeypatch.setattr(local_rank_grid_service, "_credential_owner", lambda *_args: "platform")
    run, _created = local_rank_grid_service.create_run(
        db_session,
        tenant_id=organization.id,
        organization_id=organization.id,
        created_by_user_id=None,
        campaign_id=campaign.id,
        keyword_ids=[keywords[0].id, keywords[1].id, third_keyword.id],
        grid_size=7,
        radius_miles=5,
        idempotency_key="grid-mid-batch-downgrade",
    )

    class DowngradingProvider:
        calls = 0

        def submit(self, requests):
            self.calls += 1
            apply_commercial_plan(
                db_session,
                organization_id=organization.id,
                plan_code="solo",
            )
            return [
                {
                    "point_id": item.point_id,
                    "task_id": f"terminal-{item.point_id}",
                    "status": "ranked",
                    "rank": 4,
                    "status_code": 20000,
                    "status_message": "complete",
                    "cost": Decimal("0.001"),
                }
                for item in requests
            ]

    provider = DowngradingProvider()
    monkeypatch.setattr(local_rank_grid_service, "_provider_for_run", lambda *_args: provider)

    result = local_rank_grid_service.dispatch_run(
        db_session, run_id=run.id, tenant_id=organization.id
    )

    assert provider.calls == 1
    assert result == {"run_id": run.id, "submitted": 100, "status": "partial"}
    db_session.refresh(run)
    assert run.completed_checks == 147
    assert run.failed_checks == 47
    assert run.completed_at is not None
    assert Decimal(run.provider_reported_cost) == Decimal("0.10000000")
    assert (
        db_session.query(CostLedgerEntry)
        .filter(
            CostLedgerEntry.reservation_id == run.reservation_id,
            CostLedgerEntry.event_type == "reconciliation",
        )
        .count()
        == 1
    )
    assert (
        db_session.query(CostLedgerEntry)
        .filter(
            CostLedgerEntry.reservation_id == run.reservation_id,
            CostLedgerEntry.event_type == "release",
        )
        .count()
        == 0
    )


def test_grid_provider_timeout_retains_conservative_cost_exposure(
    db_session, create_test_org, monkeypatch
) -> None:
    organization = create_test_org(name="Rank grid timeout org")
    campaign, _location, keywords = _location_campaign(
        db_session, organization, name="Timeout Grid Shop", city="Reno"
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
        idempotency_key="grid-provider-timeout",
    )
    reservation = db_session.get(CostLedgerEntry, run.reservation_id)
    estimated_cost = Decimal(reservation.estimated_cost)

    class TimeoutProvider:
        calls = 0

        def submit(self, _requests):
            self.calls += 1
            raise TimeoutError("provider response was not received")

    provider = TimeoutProvider()
    monkeypatch.setattr(local_rank_grid_service, "_provider_for_run", lambda *_args: provider)

    result = local_rank_grid_service.dispatch_run(
        db_session, run_id=run.id, tenant_id=organization.id
    )

    assert provider.calls == 1
    assert result == {"run_id": run.id, "submitted": 0, "status": "failed"}
    reconciliation = (
        db_session.query(CostLedgerEntry)
        .filter(
            CostLedgerEntry.reservation_id == run.reservation_id,
            CostLedgerEntry.event_type == "reconciliation",
        )
        .one()
    )
    assert Decimal(reconciliation.provider_reported_cost) == estimated_cost
    assert (
        db_session.query(CostLedgerEntry)
        .filter(
            CostLedgerEntry.reservation_id == run.reservation_id,
            CostLedgerEntry.event_type == "release",
        )
        .count()
        == 0
    )
    credits = get_customer_credit_summary(db_session, organization_id=organization.id)["credits"]
    assert credits["reserved"] == 0
    assert credits["used"] > 0


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

    monkeypatch.setattr(
        local_rank_grid_service, "_provider_for_run", lambda *_args: FailedProvider()
    )
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


def test_grid_reuses_each_result_to_compare_confirmed_competitors(
    db_session, create_test_org, monkeypatch
) -> None:
    organization = create_test_org(name="Rank grid competitor org")
    campaign, _location, keywords = _location_campaign(
        db_session, organization, name="Reno Owner", city="Reno"
    )
    competitor = Competitor(
        tenant_id=organization.id,
        campaign_id=campaign.id,
        domain="reno-rival.example",
        label="Reno Rival",
        discovery_source="manual",
        review_status="confirmed",
    )
    db_session.add(competitor)
    db_session.commit()
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
        idempotency_key="competitor-grid-001",
    )

    class ReadyProvider:
        def submit(self, requests):
            return [
                {
                    "point_id": item.point_id,
                    "task_id": f"ready-{item.point_id}",
                    "status": "pending",
                    "status_code": 20100,
                    "status_message": "queued",
                    "cost": Decimal("0"),
                }
                for item in requests
            ]

        def fetch(self, task_id):
            return {
                "task_id": task_id,
                "status": "ready",
                "status_code": 20000,
                "status_message": "complete",
                "cost": Decimal("0"),
                "items": [
                    {
                        "type": "maps_search",
                        "title": "Reno Rival",
                        "domain": "reno-rival.example",
                        "rank_absolute": 2,
                    },
                    {
                        "type": "maps_search",
                        "title": "Reno Owner",
                        "domain": campaign.domain,
                        "rank_absolute": 5,
                    },
                ],
            }

    provider = ReadyProvider()
    monkeypatch.setattr(local_rank_grid_service, "_provider_for_run", lambda *_args: provider)
    local_rank_grid_service.dispatch_run(db_session, run_id=run.id, tenant_id=organization.id)
    local_rank_grid_service.refresh_run(
        db_session,
        tenant_id=organization.id,
        organization_id=organization.id,
        run_id=run.id,
    )

    saved = (
        db_session.query(LocalRankGridCompetitorPoint)
        .filter(LocalRankGridCompetitorPoint.run_id == run.id)
        .all()
    )
    assert len(saved) == 9
    assert all(row.rank == 2 and row.status == "ranked" for row in saved)
    payload = local_rank_grid_service.serialize_run(db_session, run)
    assert payload["competitors"] == [
        {"id": competitor.id, "domain": "reno-rival.example", "label": "Reno Rival"}
    ]
    assert len(payload["competitor_points"]) == 9
    summary = payload["competitor_overlap_summary"][0]
    assert summary["comparable_points"] == 9
    assert summary["owner_ahead"] == 0
    assert summary["competitor_ahead"] == 9
    assert summary["tied"] == 0


def test_refresh_preserves_submitting_marker_while_later_batches_are_queued(
    db_session,
    create_test_org,
    monkeypatch,
) -> None:
    organization = create_test_org(name="Rank grid refresh fence org")
    campaign, _location, keywords = _location_campaign(
        db_session,
        organization,
        name="Refresh Fence Shop",
        city="Reno",
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
        idempotency_key="grid-refresh-preserves-dispatch-claim",
    )
    first = (
        db_session.query(LocalRankGridPoint)
        .filter(LocalRankGridPoint.run_id == run.id)
        .order_by(LocalRankGridPoint.grid_index)
        .first()
    )
    run.status = "submitting"
    first.status = "pending"
    first.provider_task_id = f"pending-{first.id}"
    db_session.commit()

    class StillPendingProvider:
        def fetch(self, task_id):
            return {
                "task_id": task_id,
                "status": "pending",
                "status_code": 20100,
                "status_message": "queued",
                "cost": Decimal("0"),
            }

    monkeypatch.setattr(
        local_rank_grid_service,
        "_provider_for_run",
        lambda *_args: StillPendingProvider(),
    )
    refreshed = local_rank_grid_service.refresh_run(
        db_session,
        tenant_id=organization.id,
        organization_id=organization.id,
        run_id=run.id,
    )

    assert refreshed.status == "submitting"
    assert (
        db_session.query(LocalRankGridPoint)
        .filter(LocalRankGridPoint.run_id == run.id, LocalRankGridPoint.status == "queued")
        .count()
        == 8
    )


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
    assert run["measurement_contract"]["id"] == "local_grid.position"
    assert run["measurement_contract"]["grid_definition_hash"] != "legacy"
    assert len(run["visibility_summary"]) == 2
    assert all("top_3_share" in item for item in run["visibility_summary"])

    replayed = client.post(
        "/api/v1/local/rank-grid/runs",
        headers=headers,
        json=create_payload,
    )
    assert replayed.status_code == 202
    assert replayed.json()["data"]["created"] is False
    assert replayed.json()["data"]["run"]["id"] == run["id"]
    assert replayed.json()["data"]["run"]["status"] == "completed"

    history = client.get(f"/api/v1/local/rank-grid/runs?campaign_id={campaign.id}", headers=headers)
    assert history.status_code == 200
    assert history.json()["data"]["items"][0]["id"] == run["id"]

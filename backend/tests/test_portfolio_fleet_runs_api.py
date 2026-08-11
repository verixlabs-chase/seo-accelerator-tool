from __future__ import annotations

from datetime import UTC, datetime

from app.models.audit_log import AuditLog
from app.models.campaign import Campaign
from app.models.fleet_job import FleetJob, FleetJobStatus, FleetJobType
from app.models.fleet_job_item import FleetJobItem, FleetJobItemStatus
from app.models.organization import Organization
from app.models.portfolio import Portfolio
from app.services.fleet_service import create_schedule_job, process_fleet_job_item


def _login(client, email: str, password: str) -> tuple[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    return data["access_token"], data["user"]["organization_id"]


def _create_location(client, *, token: str, organization_id: str, name: str) -> dict:
    response = client.post(
        f"/api/v1/organizations/{organization_id}/business-locations",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": name,
            "domain": f"{name.lower().replace(' ', '-')}.example.com",
            "city": "Dallas",
            "region": "Texas",
        },
    )
    assert response.status_code == 200
    return response.json()["data"]["business_location"]


def _add_campaigns(db_session, *, organization_id: str, locations: list[dict]) -> None:
    portfolios = {
        row.business_location_id: row
        for row in db_session.query(Portfolio)
        .filter(
            Portfolio.organization_id == organization_id,
            Portfolio.business_location_id.in_([location["id"] for location in locations]),
        )
        .all()
    }
    db_session.add_all(
        [
            Campaign(
                tenant_id=organization_id,
                organization_id=organization_id,
                business_location_id=location["id"],
                portfolio_id=portfolios[location["id"]].id,
                name=f"{location['name']} SEO",
                domain=location["domain"],
                setup_state="Active",
            )
            for location in locations
        ]
    )
    db_session.commit()


def test_portfolio_fleet_preflight_approval_progress_and_failed_only_retry(
    client,
    db_session,
) -> None:
    token, org_id = _login(client, "org-admin@example.com", "pass-org-admin")
    organization = db_session.get(Organization, org_id)
    organization.plan_type = "multi_location"
    db_session.commit()
    headers = {"Authorization": f"Bearer {token}"}
    locations = [
        _create_location(
            client,
            token=token,
            organization_id=org_id,
            name="Dallas North",
        ),
        _create_location(
            client,
            token=token,
            organization_id=org_id,
            name="Dallas South",
        ),
    ]
    _add_campaigns(db_session, organization_id=org_id, locations=locations)

    snapshot_response = client.post(
        f"/api/v1/organizations/{org_id}/target-snapshots",
        headers=headers,
        json={
            "action_key": "portfolio_review",
            "request_key": "fleet-target-1",
            "included_location_ids": [location["id"] for location in locations],
        },
    )
    assert snapshot_response.status_code == 201
    snapshot = snapshot_response.json()["data"]["target_snapshot"]

    run_payload = {
        "target_snapshot_id": snapshot["id"],
        "request_key": "fleet-run-1",
    }
    preflight_response = client.post(
        f"/api/v1/organizations/{org_id}/portfolio-fleet-runs",
        headers=headers,
        json=run_payload,
    )
    assert preflight_response.status_code == 201
    preflight_data = preflight_response.json()["data"]
    assert preflight_data["created"] is True
    run = preflight_data["portfolio_fleet_run"]
    assert run["status"] == "awaiting_approval"
    assert run["status_label"] == "Ready for approval"
    assert run["counts"] == {
        "targeted": 2,
        "ready": 2,
        "blocked": 0,
        "queued": 0,
        "running": 0,
        "succeeded": 0,
        "failed": 0,
    }
    assert run["estimated_credits"] == 0
    assert run["preflight"]["credits"]["estimated"] == 0
    assert run["preflight"]["target_snapshot"]["hash"] == snapshot["target_hash"]
    assert run["provider_changes_enabled"] is False
    assert run["can_approve"] is True

    replay_response = client.post(
        f"/api/v1/organizations/{org_id}/portfolio-fleet-runs",
        headers=headers,
        json=run_payload,
    )
    assert replay_response.status_code == 201
    assert replay_response.json()["data"]["created"] is False
    assert replay_response.json()["meta"]["idempotent_replay"] is True

    approval_response = client.post(
        f"/api/v1/organizations/{org_id}/portfolio-fleet-runs/{run['id']}/approve",
        headers=headers,
        json={"expected_version": run["version"]},
    )
    assert approval_response.status_code == 200
    approved = approval_response.json()["data"]["portfolio_fleet_run"]
    assert approved["status"] == "running"
    assert approved["approval"]["approved"] is True
    assert approved["counts"]["queued"] == 2

    jobs = (
        db_session.query(FleetJob)
        .filter(FleetJob.organization_id == org_id)
        .order_by(FleetJob.created_at.asc(), FleetJob.id.asc())
        .all()
    )
    assert len(jobs) == 2
    assert all(job.job_type == FleetJobType.PORTFOLIO_REVIEW for job in jobs)
    assert all(
        job.request_payload["items"][0]["payload"]["provider_mutation"] is False
        for job in jobs
    )

    first_item = (
        db_session.query(FleetJobItem)
        .filter(FleetJobItem.fleet_job_id == jobs[0].id)
        .one()
    )
    result = process_fleet_job_item(db=db_session, fleet_job_item_id=first_item.id)
    assert result["status"] == "succeeded"

    failed_job = db_session.get(FleetJob, jobs[1].id)
    failed_item = (
        db_session.query(FleetJobItem)
        .filter(FleetJobItem.fleet_job_id == failed_job.id)
        .one()
    )
    failed_item.status = FleetJobItemStatus.FAILED
    failed_item.error_code = "forced_test_failure"
    failed_item.error_detail = "provider details that should not reach the customer"
    failed_item.finished_at = datetime.now(UTC)
    failed_job.status = FleetJobStatus.FAILED
    failed_job.queued_items = 0
    failed_job.running_items = 0
    failed_job.succeeded_items = 0
    failed_job.failed_items = 1
    failed_job.finished_at = datetime.now(UTC)
    db_session.commit()

    progress_response = client.get(
        f"/api/v1/organizations/{org_id}/portfolio-fleet-runs/{run['id']}",
        headers=headers,
    )
    assert progress_response.status_code == 200
    progress = progress_response.json()["data"]["portfolio_fleet_run"]
    assert progress["status"] == "partial"
    assert progress["counts"]["succeeded"] == 1
    assert progress["counts"]["failed"] == 1
    failed_location = next(item for item in progress["items"] if item["status"] == "failed")
    assert "provider details" not in failed_location["message"]
    assert progress["can_retry_failed"] is True

    retry_response = client.post(
        f"/api/v1/organizations/{org_id}/portfolio-fleet-runs/{run['id']}/retry-failed",
        headers=headers,
        json={"expected_version": progress["version"]},
    )
    assert retry_response.status_code == 200
    retried = retry_response.json()["data"]["portfolio_fleet_run"]
    assert retried["status"] == "running"
    assert retried["counts"]["queued"] == 1
    assert retried["counts"]["failed"] == 0
    assert sum(item["retries"] for item in retried["items"]) == 1

    events = {
        row.event_type
        for row in db_session.query(AuditLog)
        .filter(AuditLog.tenant_id == org_id)
        .all()
    }
    assert "portfolio.fleet_run.preflight_created" in events
    assert "portfolio.fleet_run.approved" in events
    assert "portfolio.fleet_run.failed_locations_retried" in events


def test_portfolio_fleet_runs_are_organization_scoped(client, db_session) -> None:
    token_a, org_a = _login(client, "org-admin@example.com", "pass-org-admin")
    token_b, org_b = _login(client, "b@example.com", "pass-b")
    organization_a = db_session.get(Organization, org_a)
    organization_b = db_session.get(Organization, org_b)
    organization_a.plan_type = "multi_location"
    organization_b.plan_type = "multi_location"
    db_session.commit()
    location = _create_location(
        client,
        token=token_a,
        organization_id=org_a,
        name="Scoped location",
    )
    _add_campaigns(db_session, organization_id=org_a, locations=[location])
    snapshot_response = client.post(
        f"/api/v1/organizations/{org_a}/target-snapshots",
        headers={"Authorization": f"Bearer {token_a}"},
        json={
            "action_key": "portfolio_review",
            "request_key": "scoped-fleet-target",
            "included_location_ids": [location["id"]],
        },
    )
    snapshot_id = snapshot_response.json()["data"]["target_snapshot"]["id"]

    cross_org_response = client.post(
        f"/api/v1/organizations/{org_a}/portfolio-fleet-runs",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"target_snapshot_id": snapshot_id, "request_key": "cross-org-run"},
    )
    assert cross_org_response.status_code == 403

    hidden_snapshot_response = client.post(
        f"/api/v1/organizations/{org_b}/portfolio-fleet-runs",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"target_snapshot_id": snapshot_id, "request_key": "hidden-run"},
    )
    assert hidden_snapshot_response.status_code == 404
    assert (
        hidden_snapshot_response.json()["errors"][0]["details"]["reason_code"]
        == "target_snapshot_not_found"
    )

    organization_b.plan_type = "solo"
    db_session.commit()
    gated_response = client.post(
        f"/api/v1/organizations/{org_b}/portfolio-fleet-runs",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"target_snapshot_id": snapshot_id, "request_key": "solo-plan-run"},
    )
    assert gated_response.status_code == 403
    assert (
        gated_response.json()["errors"][0]["details"]["reason_code"]
        == "fleet_feature_upgrade_required"
    )


def test_existing_fleet_creation_still_commits_and_replays(client, db_session) -> None:
    token, org_id = _login(client, "org-admin@example.com", "pass-org-admin")
    location = _create_location(
        client,
        token=token,
        organization_id=org_id,
        name="Fleet regression location",
    )
    portfolio = (
        db_session.query(Portfolio)
        .filter(
            Portfolio.organization_id == org_id,
            Portfolio.business_location_id == location["id"],
        )
        .one()
    )
    job, created = create_schedule_job(
        db=db_session,
        organization_id=org_id,
        portfolio_id=portfolio.id,
        user_id=None,
        idempotency_key="schedule-regression-1",
        item_seeds=[{"item_key": "location:one", "payload": {"test": True}}],
    )
    assert created is True
    assert db_session.get(FleetJob, job.id) is not None

    replay, replay_created = create_schedule_job(
        db=db_session,
        organization_id=org_id,
        portfolio_id=portfolio.id,
        user_id=None,
        idempotency_key="schedule-regression-1",
        item_seeds=[{"item_key": "location:one", "payload": {"test": True}}],
    )
    assert replay_created is False
    assert replay.id == job.id

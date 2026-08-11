from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.business_location import BusinessLocation
from app.models.campaign import Campaign
from app.models.fleet_job import FleetJob, FleetJobStatus
from app.models.fleet_job_item import FleetJobItem, FleetJobItemStatus
from app.models.organization import Organization
from app.models.portfolio import Portfolio, PortfolioStatus
from app.models.portfolio_fleet_run import PortfolioFleetRun, PortfolioFleetRunItem
from app.models.portfolio_targeting import PortfolioTargetSnapshot
from app.services.audit_service import write_audit_log
from app.services.cost_economics_service import (
    CostEconomicsError,
    get_customer_credit_summary,
    resolve_plan_economics,
)
from app.services.fleet_service import (
    enqueue_pending_items_for_portfolio,
    prepare_portfolio_review_job,
    retry_failed_items,
)


SUPPORTED_ACTIONS: dict[str, dict[str, Any]] = {
    "portfolio_review": {
        "label": "Review location readiness",
        "description": (
            "Check that every selected location still has its own active workspace "
            "before any future bulk action is offered."
        ),
        "estimated_credit_units_per_location": 0,
        "provider_mutation": False,
    }
}


class PortfolioFleetError(RuntimeError):
    def __init__(self, reason_code: str, *, status_code: int = 400) -> None:
        self.reason_code = reason_code
        self.status_code = status_code
        super().__init__(reason_code)


def create_portfolio_fleet_run(
    db: Session,
    *,
    organization_id: str,
    actor_user_id: str,
    target_snapshot_id: str,
    request_key: str,
) -> tuple[PortfolioFleetRun, bool]:
    normalized_request_key = request_key.strip()
    if not normalized_request_key:
        raise PortfolioFleetError("fleet_request_key_required", status_code=422)
    _assert_bulk_feature_plan(db, organization_id=organization_id)

    snapshot = _snapshot_or_error(
        db,
        organization_id=organization_id,
        target_snapshot_id=target_snapshot_id,
    )
    policy = SUPPORTED_ACTIONS.get(snapshot.action_key)
    if policy is None:
        raise PortfolioFleetError("fleet_action_not_supported", status_code=422)

    existing = (
        db.query(PortfolioFleetRun)
        .filter(
            PortfolioFleetRun.organization_id == organization_id,
            PortfolioFleetRun.request_key == normalized_request_key,
        )
        .first()
    )
    if existing is not None:
        if (
            existing.target_snapshot_id != snapshot.id
            or existing.target_hash != snapshot.target_hash
            or existing.action_key != snapshot.action_key
        ):
            raise PortfolioFleetError("fleet_request_key_conflict", status_code=409)
        _sync_run_from_jobs(db, existing)
        return existing, False

    now = datetime.now(UTC)
    allowance = get_customer_credit_summary(db, organization_id=organization_id, now=now)
    capability_rows = _build_capability_rows(
        db,
        organization_id=organization_id,
        snapshot=snapshot,
        policy=policy,
    )
    ready_rows = [row for row in capability_rows if row["ready"]]
    runtime_blocked = [row for row in capability_rows if not row["ready"]]
    frozen_blocked = [
        dict(item)
        for item in list(snapshot.exceptions_json or [])
        if bool(item.get("blocked"))
    ]
    estimated_credits = sum(int(row["estimated_credit_units"]) for row in ready_rows)
    blocked_count = len(runtime_blocked) + len(frozen_blocked)
    status = "awaiting_approval" if ready_rows else "blocked"

    run = PortfolioFleetRun(
        id=str(uuid.uuid4()),
        tenant_id=organization_id,
        organization_id=organization_id,
        target_snapshot_id=snapshot.id,
        action_key=snapshot.action_key,
        request_key=normalized_request_key,
        target_hash=snapshot.target_hash,
        status=status,
        preflight_json=_preflight_payload(
            snapshot=snapshot,
            policy=policy,
            ready_rows=ready_rows,
            runtime_blocked=runtime_blocked,
            frozen_blocked=frozen_blocked,
            estimated_credits=estimated_credits,
            allowance=allowance,
        ),
        target_count=int(snapshot.target_count) + int(snapshot.blocked_count),
        ready_count=len(ready_rows),
        blocked_count=blocked_count,
        queued_count=0,
        running_count=0,
        succeeded_count=0,
        failed_count=0,
        estimated_credit_units=estimated_credits,
        requested_by_user_id=actor_user_id,
        version=1,
        created_at=now,
        updated_at=now,
    )
    db.add(run)
    db.flush()

    for capability in capability_rows:
        db.add(
            PortfolioFleetRunItem(
                id=str(uuid.uuid4()),
                tenant_id=organization_id,
                organization_id=organization_id,
                portfolio_fleet_run_id=run.id,
                business_location_id=capability["business_location_id"],
                campaign_id=capability.get("campaign_id"),
                portfolio_id=capability.get("portfolio_id"),
                item_key=f"location:{capability['business_location_id']}",
                location_name=capability["location_name"],
                status="ready" if capability["ready"] else "blocked",
                capability_json=capability,
                estimated_credit_units=int(capability["estimated_credit_units"]),
                error_code=None if capability["ready"] else capability["reason_code"],
                error_detail=None if capability["ready"] else capability["message"],
                retries=0,
                created_at=now,
                updated_at=now,
            )
        )

    write_audit_log(
        db,
        tenant_id=organization_id,
        actor_user_id=actor_user_id,
        event_type="portfolio.fleet_run.preflight_created",
        payload={
            "organization_id": organization_id,
            "portfolio_fleet_run_id": run.id,
            "target_snapshot_id": snapshot.id,
            "target_hash": snapshot.target_hash,
            "action_key": snapshot.action_key,
            "ready_count": run.ready_count,
            "blocked_count": run.blocked_count,
            "estimated_credit_units": estimated_credits,
            "provider_mutation": False,
        },
    )
    db.flush()
    return run, True


def approve_portfolio_fleet_run(
    db: Session,
    *,
    organization_id: str,
    run_id: str,
    actor_user_id: str,
    expected_version: int,
) -> PortfolioFleetRun:
    run = _locked_run_or_error(db, organization_id=organization_id, run_id=run_id)
    _assert_bulk_feature_plan(db, organization_id=organization_id)
    if run.version != expected_version:
        raise PortfolioFleetError("fleet_run_version_conflict", status_code=409)
    if run.status == "blocked":
        raise PortfolioFleetError("fleet_run_has_no_ready_locations", status_code=409)
    if run.status != "awaiting_approval":
        raise PortfolioFleetError("fleet_run_not_awaiting_approval", status_code=409)

    snapshot = _snapshot_or_error(
        db,
        organization_id=organization_id,
        target_snapshot_id=run.target_snapshot_id,
    )
    if snapshot.target_hash != run.target_hash:
        raise PortfolioFleetError("fleet_target_snapshot_changed", status_code=409)

    allowance = get_customer_credit_summary(
        db,
        organization_id=organization_id,
        now=datetime.now(UTC),
    )
    remaining_credits = int((allowance.get("credits") or {}).get("remaining") or 0)
    if run.estimated_credit_units > remaining_credits:
        raise PortfolioFleetError("fleet_credit_allowance_exhausted", status_code=402)

    policy = SUPPORTED_ACTIONS[run.action_key]
    current_capabilities = {
        row["business_location_id"]: row
        for row in _build_capability_rows(
            db,
            organization_id=organization_id,
            snapshot=snapshot,
            policy=policy,
        )
    }
    rows = _run_items(db, run.id)
    portfolio_ids: set[str] = set()
    now = datetime.now(UTC)
    for item in rows:
        capability = current_capabilities.get(item.business_location_id)
        if capability is None or not capability["ready"]:
            item.status = "blocked"
            item.capability_json = capability or {
                "ready": False,
                "reason_code": "location_no_longer_available",
                "message": "This location is no longer available for this run.",
            }
            item.error_code = item.capability_json["reason_code"]
            item.error_detail = item.capability_json["message"]
            item.updated_at = now
            continue

        item.campaign_id = capability["campaign_id"]
        item.portfolio_id = capability["portfolio_id"]
        item.capability_json = capability
        job, _created = prepare_portfolio_review_job(
            db=db,
            organization_id=organization_id,
            portfolio_id=capability["portfolio_id"],
            user_id=actor_user_id,
            idempotency_key=f"portfolio-run:{run.id}:{item.business_location_id}",
            item_seed={
                "item_key": item.item_key,
                "payload": {
                    "portfolio_fleet_run_id": run.id,
                    "business_location_id": item.business_location_id,
                    "campaign_id": capability["campaign_id"],
                    "action_key": run.action_key,
                    "provider_mutation": False,
                },
            },
        )
        item.fleet_job_id = job.id
        item.status = "queued"
        item.error_code = None
        item.error_detail = None
        item.updated_at = now
        portfolio_ids.add(capability["portfolio_id"])

    ready_count = sum(1 for item in rows if item.status != "blocked")
    runtime_blocked = sum(1 for item in rows if item.status == "blocked")
    frozen_blocked = sum(
        1
        for item in list(snapshot.exceptions_json or [])
        if bool(item.get("blocked"))
    )
    if ready_count == 0:
        raise PortfolioFleetError("fleet_run_has_no_ready_locations", status_code=409)

    run.ready_count = ready_count
    run.blocked_count = frozen_blocked + runtime_blocked
    run.queued_count = ready_count
    run.running_count = 0
    run.succeeded_count = 0
    run.failed_count = 0
    run.status = "running"
    run.approved_by_user_id = actor_user_id
    run.approved_at = now
    run.started_at = now
    run.updated_at = now
    run.version += 1
    write_audit_log(
        db,
        tenant_id=organization_id,
        actor_user_id=actor_user_id,
        event_type="portfolio.fleet_run.approved",
        payload={
            "organization_id": organization_id,
            "portfolio_fleet_run_id": run.id,
            "target_snapshot_id": run.target_snapshot_id,
            "target_hash": run.target_hash,
            "action_key": run.action_key,
            "ready_count": ready_count,
            "blocked_count": run.blocked_count,
            "estimated_credit_units": run.estimated_credit_units,
            "provider_mutation": False,
        },
    )
    db.commit()

    for portfolio_id in sorted(portfolio_ids):
        try:
            enqueue_pending_items_for_portfolio(
                db=db,
                organization_id=organization_id,
                portfolio_id=portfolio_id,
            )
        except Exception:  # noqa: BLE001
            # The durable queued row is the recovery source if the broker is unavailable.
            continue
    db.refresh(run)
    return run


def retry_failed_portfolio_fleet_run_items(
    db: Session,
    *,
    organization_id: str,
    run_id: str,
    actor_user_id: str,
    expected_version: int,
) -> PortfolioFleetRun:
    run = get_portfolio_fleet_run(
        db,
        organization_id=organization_id,
        run_id=run_id,
        sync=True,
    )
    if run.version != expected_version:
        raise PortfolioFleetError("fleet_run_version_conflict", status_code=409)
    failed_items = [item for item in _run_items(db, run.id) if item.status == "failed"]
    if not failed_items:
        raise PortfolioFleetError("fleet_run_has_no_failed_locations", status_code=409)

    retried = 0
    for item in failed_items:
        if not item.fleet_job_id:
            continue
        retried_for_job = retry_failed_items(
            db=db,
            organization_id=organization_id,
            fleet_job_id=item.fleet_job_id,
        )
        if retried_for_job:
            item.status = "queued"
            item.retries += 1
            item.error_code = None
            item.error_detail = None
            item.updated_at = datetime.now(UTC)
            retried += 1
    if retried == 0:
        raise PortfolioFleetError("fleet_run_retry_not_available", status_code=409)

    run.status = "running"
    run.queued_count += retried
    run.failed_count = max(0, run.failed_count - retried)
    run.finished_at = None
    run.updated_at = datetime.now(UTC)
    run.version += 1
    write_audit_log(
        db,
        tenant_id=organization_id,
        actor_user_id=actor_user_id,
        event_type="portfolio.fleet_run.failed_locations_retried",
        payload={
            "organization_id": organization_id,
            "portfolio_fleet_run_id": run.id,
            "retried_location_count": retried,
        },
    )
    db.commit()
    db.refresh(run)
    return run


def pause_portfolio_fleet_run(
    db: Session,
    *,
    organization_id: str,
    run_id: str,
    actor_user_id: str,
    expected_version: int,
) -> PortfolioFleetRun:
    run = _locked_run_or_error(db, organization_id=organization_id, run_id=run_id)
    if run.version != expected_version:
        raise PortfolioFleetError("fleet_run_version_conflict", status_code=409)
    _sync_run_from_jobs(db, run)
    if run.status != "running":
        raise PortfolioFleetError("fleet_run_not_running", status_code=409)
    if run.queued_count < 1:
        raise PortfolioFleetError("fleet_run_has_no_waiting_locations", status_code=409)

    now = datetime.now(UTC)
    run.status = "paused"
    run.updated_at = now
    run.version += 1
    write_audit_log(
        db,
        tenant_id=organization_id,
        actor_user_id=actor_user_id,
        event_type="portfolio.fleet_run.paused",
        payload={
            "organization_id": organization_id,
            "portfolio_fleet_run_id": run.id,
            "target_hash": run.target_hash,
            "waiting_location_count": run.queued_count,
            "completed_location_count": run.succeeded_count,
        },
    )
    db.commit()
    db.refresh(run)
    return run


def resume_portfolio_fleet_run(
    db: Session,
    *,
    organization_id: str,
    run_id: str,
    actor_user_id: str,
    expected_version: int,
) -> PortfolioFleetRun:
    run = _locked_run_or_error(db, organization_id=organization_id, run_id=run_id)
    if run.version != expected_version:
        raise PortfolioFleetError("fleet_run_version_conflict", status_code=409)
    if run.status != "paused":
        raise PortfolioFleetError("fleet_run_not_paused", status_code=409)

    _sync_run_from_jobs(db, run, allow_paused=True)
    if run.status == "paused":
        # Defensive fallback for a run without linked jobs.
        run.status = "running"
        run.updated_at = datetime.now(UTC)
        run.version += 1
    portfolio_ids = {
        item.portfolio_id
        for item in _run_items(db, run.id)
        if item.portfolio_id and item.status == "queued"
    }
    write_audit_log(
        db,
        tenant_id=organization_id,
        actor_user_id=actor_user_id,
        event_type="portfolio.fleet_run.resumed",
        payload={
            "organization_id": organization_id,
            "portfolio_fleet_run_id": run.id,
            "target_hash": run.target_hash,
            "waiting_location_count": run.queued_count,
            "current_status": run.status,
        },
    )
    db.commit()

    if run.status == "running":
        for portfolio_id in sorted(portfolio_ids):
            try:
                enqueue_pending_items_for_portfolio(
                    db=db,
                    organization_id=organization_id,
                    portfolio_id=portfolio_id,
                )
            except Exception:  # noqa: BLE001
                continue
    db.refresh(run)
    return run


def list_portfolio_fleet_runs(
    db: Session,
    *,
    organization_id: str,
    limit: int = 10,
    location_group_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    query = db.query(PortfolioFleetRun).filter(
        PortfolioFleetRun.organization_id == organization_id
    )
    if location_group_ids is not None:
        if not location_group_ids:
            return []
        query = query.join(
            PortfolioTargetSnapshot,
            PortfolioTargetSnapshot.id == PortfolioFleetRun.target_snapshot_id,
        ).filter(PortfolioTargetSnapshot.location_group_id.in_(location_group_ids))
    rows = query.order_by(
        PortfolioFleetRun.created_at.desc(), PortfolioFleetRun.id.desc()
    ).limit(limit).all()
    changed = False
    for row in rows:
        changed = _sync_run_from_jobs(db, row) or changed
    if changed:
        db.commit()
    return [serialize_portfolio_fleet_run(db, row) for row in rows]


def get_portfolio_fleet_run(
    db: Session,
    *,
    organization_id: str,
    run_id: str,
    sync: bool = True,
) -> PortfolioFleetRun:
    row = _run_or_error(db, organization_id=organization_id, run_id=run_id)
    if sync and _sync_run_from_jobs(db, row):
        db.commit()
        db.refresh(row)
    return row


def serialize_portfolio_fleet_run(
    db: Session,
    row: PortfolioFleetRun,
) -> dict[str, Any]:
    items = _run_items(db, row.id)
    return {
        "id": row.id,
        "organization_id": row.organization_id,
        "target_snapshot_id": row.target_snapshot_id,
        "action_key": row.action_key,
        "request_key": row.request_key,
        "target_hash": row.target_hash,
        "status": row.status,
        "status_label": _status_label(row.status),
        "preflight": row.preflight_json,
        "counts": {
            "targeted": row.target_count,
            "ready": row.ready_count,
            "blocked": row.blocked_count,
            "queued": row.queued_count,
            "running": row.running_count,
            "succeeded": row.succeeded_count,
            "failed": row.failed_count,
        },
        "estimated_credits": row.estimated_credit_units,
        "approval": {
            "required": True,
            "approved": row.approved_at is not None,
            "approved_by_user_id": row.approved_by_user_id,
            "approved_at": row.approved_at.isoformat() if row.approved_at else None,
        },
        "version": row.version,
        "created_at": row.created_at.isoformat(),
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        "items": [
            {
                "id": item.id,
                "business_location_id": item.business_location_id,
                "location_name": item.location_name,
                "campaign_id": item.campaign_id,
                "status": item.status,
                "status_label": _item_status_label(item.status),
                "estimated_credits": item.estimated_credit_units,
                "retries": item.retries,
                "message": _item_message(item),
            }
            for item in items
        ],
        "can_approve": (
            row.status == "awaiting_approval"
            and row.ready_count > 0
            and bool((row.preflight_json.get("credits") or {}).get("confirmed"))
        ),
        "can_pause": row.status == "running" and row.queued_count > 0,
        "can_resume": row.status == "paused",
        "can_retry_failed": row.failed_count > 0 and row.status != "paused",
        "provider_changes_enabled": False,
    }


def _build_capability_rows(
    db: Session,
    *,
    organization_id: str,
    snapshot: PortfolioTargetSnapshot,
    policy: dict[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for target in list(snapshot.targets_json or []):
        location_id = str(target.get("location_id") or "")
        location_name = str(target.get("location_name") or "Location")
        campaign_id = str(target.get("campaign_id") or "")
        location = (
            db.query(BusinessLocation)
            .filter(
                BusinessLocation.organization_id == organization_id,
                BusinessLocation.id == location_id,
            )
            .first()
        )
        if location is None or location.status != "active":
            rows.append(
                _blocked_capability(
                    location_id=location_id,
                    location_name=location_name,
                    campaign_id=campaign_id or None,
                    reason_code="location_not_active",
                    message="This location is no longer active.",
                )
            )
            continue
        campaign = (
            db.query(Campaign)
            .filter(
                Campaign.organization_id == organization_id,
                Campaign.id == campaign_id,
                Campaign.business_location_id == location_id,
            )
            .first()
        )
        if campaign is None or not campaign.portfolio_id:
            rows.append(
                _blocked_capability(
                    location_id=location_id,
                    location_name=location.name,
                    campaign_id=campaign_id or None,
                    reason_code="location_workspace_missing",
                    message="Finish setting up this location's workspace before continuing.",
                )
            )
            continue
        portfolio = (
            db.query(Portfolio)
            .filter(
                Portfolio.organization_id == organization_id,
                Portfolio.id == campaign.portfolio_id,
            )
            .first()
        )
        portfolio_status = (
            portfolio.status.value if portfolio and hasattr(portfolio.status, "value") else str(portfolio.status) if portfolio else ""
        )
        if portfolio is None or portfolio_status != PortfolioStatus.ACTIVE.value:
            rows.append(
                _blocked_capability(
                    location_id=location_id,
                    location_name=location.name,
                    campaign_id=campaign.id,
                    reason_code="location_workspace_inactive",
                    message="Reactivate this location's workspace before continuing.",
                )
            )
            continue
        rows.append(
            {
                "business_location_id": location.id,
                "location_name": location.name,
                "campaign_id": campaign.id,
                "portfolio_id": portfolio.id,
                "ready": True,
                "reason_code": "ready",
                "message": "Ready for the approved internal check.",
                "estimated_credit_units": int(
                    policy["estimated_credit_units_per_location"]
                ),
                "provider_mutation": False,
                "checks": {
                    "location_active": True,
                    "campaign_scoped": True,
                    "workspace_active": True,
                    "external_changes_disabled": True,
                },
            }
        )
    return rows


def _blocked_capability(
    *,
    location_id: str,
    location_name: str,
    campaign_id: str | None,
    reason_code: str,
    message: str,
) -> dict[str, Any]:
    return {
        "business_location_id": location_id,
        "location_name": location_name,
        "campaign_id": campaign_id,
        "portfolio_id": None,
        "ready": False,
        "reason_code": reason_code,
        "message": message,
        "estimated_credit_units": 0,
        "provider_mutation": False,
        "checks": {
            "location_active": reason_code != "location_not_active",
            "campaign_scoped": reason_code not in {"location_workspace_missing"},
            "workspace_active": False,
            "external_changes_disabled": True,
        },
    }


def _preflight_payload(
    *,
    snapshot: PortfolioTargetSnapshot,
    policy: dict[str, Any],
    ready_rows: list[dict[str, Any]],
    runtime_blocked: list[dict[str, Any]],
    frozen_blocked: list[dict[str, Any]],
    estimated_credits: int,
    allowance: dict[str, Any],
) -> dict[str, Any]:
    credit_summary = allowance.get("credits") or {}
    return {
        "action": {
            "key": snapshot.action_key,
            "label": policy["label"],
            "description": policy["description"],
        },
        "target_snapshot": {
            "id": snapshot.id,
            "hash": snapshot.target_hash,
            "immutable": True,
        },
        "ready_locations": [
            {
                "business_location_id": row["business_location_id"],
                "location_name": row["location_name"],
                "message": row["message"],
            }
            for row in ready_rows
        ],
        "blocked_locations": [
            {
                "business_location_id": row["business_location_id"],
                "location_name": row["location_name"],
                "reason_code": row["reason_code"],
                "message": row["message"],
            }
            for row in runtime_blocked
        ]
        + [
            {
                "business_location_id": row.get("location_id"),
                "location_name": row.get("location_name"),
                "reason_code": row.get("reason"),
                "message": row.get("message"),
            }
            for row in frozen_blocked
        ],
        "credits": {
            "name": "Insight Credits",
            "estimated": estimated_credits,
            "remaining_before_approval": int(credit_summary.get("remaining") or 0),
            "confirmed": estimated_credits <= int(credit_summary.get("remaining") or 0),
            "message": (
                "This internal readiness check uses no Insight Credits."
                if estimated_credits == 0
                else f"This run is expected to use {estimated_credits} Insight Credits."
            ),
        },
        "approval": {
            "required": True,
            "message": "Review the exact list, then approve once to start each ready location.",
        },
        "guardrails": [
            "The target list is frozen and cannot expand after approval.",
            "Every location runs in its own isolated workspace.",
            "One failed location does not hide successful locations.",
            "No Google profile or website changes are enabled in this run.",
        ],
        "provider_mutation": False,
    }


def _sync_run_from_jobs(
    db: Session,
    run: PortfolioFleetRun,
    *,
    allow_paused: bool = False,
) -> bool:
    if run.status in {"awaiting_approval", "blocked", "cancelled"}:
        return False
    preserve_pause = run.status == "paused" and not allow_paused
    items = _run_items(db, run.id)
    job_ids = [item.fleet_job_id for item in items if item.fleet_job_id]
    jobs = (
        db.query(FleetJob).filter(FleetJob.id.in_(job_ids)).all() if job_ids else []
    )
    jobs_by_id = {job.id: job for job in jobs}
    fleet_items = (
        db.query(FleetJobItem)
        .filter(FleetJobItem.fleet_job_id.in_(job_ids))
        .order_by(FleetJobItem.created_at.asc(), FleetJobItem.id.asc())
        .all()
        if job_ids
        else []
    )
    fleet_items_by_job: dict[str, FleetJobItem] = {}
    for fleet_item in fleet_items:
        fleet_items_by_job.setdefault(fleet_item.fleet_job_id, fleet_item)
    changed = False
    for item in items:
        if not item.fleet_job_id:
            continue
        job = jobs_by_id.get(item.fleet_job_id)
        if job is None:
            next_status = "failed"
            message = "The saved location job could not be found."
        else:
            fleet_item = fleet_items_by_job.get(job.id)
            if fleet_item is not None:
                next_status = {
                    FleetJobItemStatus.QUEUED.value: "queued",
                    FleetJobItemStatus.RUNNING.value: "running",
                    FleetJobItemStatus.SUCCEEDED.value: "succeeded",
                    FleetJobItemStatus.FAILED.value: "failed",
                }.get(_enum_value(fleet_item.status), item.status)
            else:
                job_status = _enum_value(job.status)
                next_status = {
                    FleetJobStatus.QUEUED.value: "queued",
                    FleetJobStatus.RUNNING.value: "running",
                    FleetJobStatus.SUCCEEDED.value: "succeeded",
                    FleetJobStatus.PARTIAL.value: "failed",
                    FleetJobStatus.FAILED.value: "failed",
                    FleetJobStatus.CANCELLED.value: "failed",
                }.get(job_status, item.status)
            message = None
        if next_status != item.status:
            item.status = next_status
            item.updated_at = datetime.now(UTC)
            changed = True
        if next_status == "failed":
            fleet_item = fleet_items_by_job.get(item.fleet_job_id)
            next_code = fleet_item.error_code if fleet_item else "location_job_missing"
            next_detail = (
                "This location did not finish. Fix the connection if needed, then retry failed locations."
                if fleet_item
                else message
            )
            if item.error_code != next_code or item.error_detail != next_detail:
                item.error_code = next_code
                item.error_detail = next_detail
                changed = True

    counts = {
        "queued": sum(1 for item in items if item.status == "queued"),
        "running": sum(1 for item in items if item.status == "running"),
        "succeeded": sum(1 for item in items if item.status == "succeeded"),
        "failed": sum(1 for item in items if item.status == "failed"),
    }
    for field, value in counts.items():
        attribute = f"{field}_count"
        if getattr(run, attribute) != value:
            setattr(run, attribute, value)
            changed = True

    next_status = run.status
    if preserve_pause and (counts["queued"] or counts["running"]):
        next_status = "paused"
    elif counts["queued"] or counts["running"]:
        next_status = "running"
    elif counts["failed"]:
        next_status = "partial" if counts["succeeded"] else "failed"
    elif counts["succeeded"]:
        next_status = "partial" if run.blocked_count else "succeeded"
    if next_status != run.status:
        run.status = next_status
        changed = True
    terminal = next_status in {"succeeded", "partial", "failed"}
    if terminal and run.finished_at is None:
        run.finished_at = datetime.now(UTC)
        changed = True
    if changed:
        run.updated_at = datetime.now(UTC)
        run.version += 1
        db.flush()
    return changed


def _snapshot_or_error(
    db: Session,
    *,
    organization_id: str,
    target_snapshot_id: str,
) -> PortfolioTargetSnapshot:
    row = (
        db.query(PortfolioTargetSnapshot)
        .filter(
            PortfolioTargetSnapshot.organization_id == organization_id,
            PortfolioTargetSnapshot.id == target_snapshot_id,
        )
        .first()
    )
    if row is None:
        raise PortfolioFleetError("target_snapshot_not_found", status_code=404)
    return row


def _assert_bulk_feature_plan(db: Session, *, organization_id: str) -> None:
    organization = db.get(Organization, organization_id)
    if organization is None:
        raise PortfolioFleetError("organization_not_found", status_code=404)
    try:
        plan = resolve_plan_economics(organization.plan_type)
    except CostEconomicsError as exc:
        raise PortfolioFleetError("fleet_feature_upgrade_required", status_code=403) from exc
    if plan.code not in {"multi_location", "enterprise"}:
        raise PortfolioFleetError("fleet_feature_upgrade_required", status_code=403)


def _run_or_error(
    db: Session,
    *,
    organization_id: str,
    run_id: str,
) -> PortfolioFleetRun:
    row = (
        db.query(PortfolioFleetRun)
        .filter(
            PortfolioFleetRun.organization_id == organization_id,
            PortfolioFleetRun.id == run_id,
        )
        .first()
    )
    if row is None:
        raise PortfolioFleetError("fleet_run_not_found", status_code=404)
    return row


def _locked_run_or_error(
    db: Session,
    *,
    organization_id: str,
    run_id: str,
) -> PortfolioFleetRun:
    row = (
        db.query(PortfolioFleetRun)
        .filter(
            PortfolioFleetRun.organization_id == organization_id,
            PortfolioFleetRun.id == run_id,
        )
        .with_for_update()
        .first()
    )
    if row is None:
        raise PortfolioFleetError("fleet_run_not_found", status_code=404)
    return row


def _run_items(db: Session, run_id: str) -> list[PortfolioFleetRunItem]:
    return (
        db.query(PortfolioFleetRunItem)
        .filter(PortfolioFleetRunItem.portfolio_fleet_run_id == run_id)
        .order_by(PortfolioFleetRunItem.location_name.asc(), PortfolioFleetRunItem.id.asc())
        .all()
    )


def _enum_value(value: object) -> str:
    return str(value.value if hasattr(value, "value") else value)


def _status_label(status: str) -> str:
    return {
        "awaiting_approval": "Ready for approval",
        "blocked": "Needs setup",
        "running": "In progress",
        "paused": "Paused",
        "succeeded": "Complete",
        "partial": "Some locations need attention",
        "failed": "Needs attention",
        "cancelled": "Stopped",
    }.get(status, status.replace("_", " ").title())


def _item_status_label(status: str) -> str:
    return {
        "ready": "Ready",
        "blocked": "Needs setup",
        "queued": "Waiting",
        "running": "In progress",
        "succeeded": "Complete",
        "failed": "Needs attention",
    }.get(status, status.title())


def _item_message(item: PortfolioFleetRunItem) -> str:
    if item.error_detail:
        return item.error_detail
    return {
        "ready": "Ready after the saved checks passed.",
        "blocked": "Finish this location's setup before starting a new run.",
        "queued": "Approved and waiting for its turn.",
        "running": "The location check is running now.",
        "succeeded": "This location finished successfully.",
        "failed": "This location did not finish. Retry it after checking the connection.",
    }.get(item.status, "Status is available.")

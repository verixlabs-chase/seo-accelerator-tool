from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.campaign import Campaign
from app.models.governed_experiment import (
    GovernedExperimentGuardrailCheck,
    GovernedExperimentPlan,
    GovernedExperimentProtocol,
)
from app.services import action_plan_measurement_service, cost_economics_service
from app.services.audit_service import write_audit_log


PROTOCOL_VERSION = "1.0"
AUTHORIZATION_ACKNOWLEDGEMENTS = (
    "reviewed_frozen_plan",
    "rollback_ready",
    "understands_no_change_is_made",
)
STOP_REASON_CODES = {
    "safety_issue",
    "primary_metric_regression",
    "protected_metric_regression",
    "data_quality_loss",
    "allowance_exhausted",
    "owner_request",
}


def list_protocols(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
) -> dict[str, Any]:
    _campaign_or_404(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=campaign_id,
    )
    rows = (
        db.query(GovernedExperimentProtocol)
        .filter(
            GovernedExperimentProtocol.tenant_id == tenant_id,
            GovernedExperimentProtocol.organization_id == organization_id,
            GovernedExperimentProtocol.campaign_id == campaign_id,
        )
        .order_by(
            GovernedExperimentProtocol.created_at.desc(),
            GovernedExperimentProtocol.id.desc(),
        )
        .all()
    )
    return {
        "items": [_serialize_protocol(db, row) for row in rows],
        "count": len(rows),
        "safety": _safety(),
    }


def prepare_protocol(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
    plan_id: str,
    actor_user_id: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    plan = _plan_or_404(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=campaign_id,
        plan_id=plan_id,
    )
    existing = (
        db.query(GovernedExperimentProtocol)
        .filter(
            GovernedExperimentProtocol.tenant_id == tenant_id,
            GovernedExperimentProtocol.plan_id == plan_id,
        )
        .first()
    )
    if existing is not None:
        return {"created": False, "protocol": _serialize_protocol(db, existing)}
    if plan.status != "approved":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Approve the controlled-test design before preparing its safety checks",
        )

    captured_at = _aware(now or datetime.now(UTC))
    baseline = _capture_metric(db, plan=plan, metric_id=plan.metric_id, at=captured_at)
    _require_available_baseline(baseline, label="main result")
    protected = [
        _capture_metric(db, plan=plan, metric_id=metric_id, at=captured_at)
        for metric_id in list(plan.guardrail_metric_ids or [])
    ]
    for item in protected:
        _require_available_baseline(item, label="protected result")
    allowance = cost_economics_service.get_customer_credit_summary(
        db, organization_id=organization_id, now=captured_at
    )
    credit_baseline = dict(allowance.get("credits") or {})
    artifact = {
        "protocol_version": PROTOCOL_VERSION,
        "plan_id": plan.id,
        "plan_artifact_hash": plan.artifact_hash,
        "baseline_snapshot": baseline,
        "protected_baselines": protected,
        "allowance_baseline": credit_baseline,
        "stop_rules": list(plan.stop_rules or []),
        "rollback_steps": list(plan.rollback_steps or []),
    }
    row = GovernedExperimentProtocol(
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=campaign_id,
        business_location_id=plan.business_location_id,
        plan_id=plan.id,
        status="prepared",
        protocol_version=PROTOCOL_VERSION,
        plan_artifact_hash=plan.artifact_hash,
        protocol_hash=_hash(artifact),
        baseline_snapshot=baseline,
        protected_baselines=protected,
        allowance_baseline=credit_baseline,
        stop_rules=list(plan.stop_rules or []),
        rollback_steps=list(plan.rollback_steps or []),
        latest_check_summary={
            "status": "not_started",
            "allowance_blocked": bool(credit_baseline.get("blocked")),
        },
        created_by_user_id=actor_user_id,
        created_at=captured_at,
        updated_at=captured_at,
    )
    db.add(row)
    db.flush()
    _audit(
        db,
        row=row,
        actor_user_id=actor_user_id,
        event_type="intelligence.governed_experiment_protocol_prepared",
        extra={"plan_artifact_hash": plan.artifact_hash},
    )
    db.commit()
    db.refresh(row)
    return {"created": True, "protocol": _serialize_protocol(db, row)}


def authorize_protocol(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
    protocol_id: str,
    actor_user_id: str,
    acknowledgements: dict[str, bool],
    note: str | None,
    now: datetime | None = None,
) -> dict[str, Any]:
    row = _protocol_or_404(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=campaign_id,
        protocol_id=protocol_id,
        lock_for_update=True,
    )
    if row.status == "authorized":
        return {"updated": False, "protocol": _serialize_protocol(db, row)}
    if row.status != "prepared":
        raise HTTPException(status_code=409, detail="This monitoring protocol cannot be authorized now")
    missing = [key for key in AUTHORIZATION_ACKNOWLEDGEMENTS if acknowledgements.get(key) is not True]
    if missing:
        raise HTTPException(
            status_code=422,
            detail="Confirm the frozen plan, undo steps, and no-change safety notice first",
        )
    plan = _plan_or_404(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=campaign_id,
        plan_id=row.plan_id,
    )
    _require_matching_plan(row, plan)
    credits = cost_economics_service.get_customer_credit_summary(
        db, organization_id=organization_id, now=now
    ).get("credits") or {}
    if credits.get("blocked"):
        raise HTTPException(status_code=409, detail="Insight Credits must be available before monitoring can be authorized")

    resolved_at = _aware(now or datetime.now(UTC))
    row.status = "authorized"
    row.authorization_acknowledgements = {
        **{key: True for key in AUTHORIZATION_ACKNOWLEDGEMENTS},
        "note_provided": bool(str(note or "").strip()),
    }
    row.authorized_by_user_id = actor_user_id
    row.authorized_at = resolved_at
    row.updated_at = resolved_at
    _audit(
        db,
        row=row,
        actor_user_id=actor_user_id,
        event_type="intelligence.governed_experiment_protocol_authorized",
        extra={"all_acknowledgements_confirmed": True},
    )
    db.commit()
    db.refresh(row)
    return {"updated": True, "protocol": _serialize_protocol(db, row)}


def start_monitoring(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
    protocol_id: str,
    actor_user_id: str,
    evidence_references: list[str],
    change_applied_at: datetime | None,
    now: datetime | None = None,
) -> dict[str, Any]:
    row = _protocol_or_404(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=campaign_id,
        protocol_id=protocol_id,
        lock_for_update=True,
    )
    if row.status == "monitoring":
        return {"updated": False, "protocol": _serialize_protocol(db, row)}
    if row.status != "authorized":
        raise HTTPException(status_code=409, detail="Authorize the monitoring protocol before starting it")
    references = _unique_nonblank(evidence_references)
    if not references:
        raise HTTPException(status_code=422, detail="Add evidence showing where the approved change was made")
    resolved_at = _aware(now or datetime.now(UTC))
    applied_at = _aware(change_applied_at or resolved_at)
    if applied_at > resolved_at:
        raise HTTPException(status_code=422, detail="The change time cannot be in the future")
    if row.authorized_at and applied_at < _aware(row.authorized_at):
        raise HTTPException(status_code=422, detail="The change must happen after monitoring was authorized")

    plan = _plan_or_404(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=campaign_id,
        plan_id=row.plan_id,
    )
    _require_matching_plan(row, plan)
    row.status = "monitoring"
    row.change_evidence = [
        {"reference": item, "change_applied_at": applied_at.isoformat()} for item in references
    ]
    row.started_by_user_id = actor_user_id
    row.monitoring_started_at = resolved_at
    row.observation_due_at = resolved_at + timedelta(days=plan.observation_window_days)
    row.latest_check_summary = {"status": "waiting_for_fresh_data", "checked_at": None}
    row.updated_at = resolved_at
    _audit(
        db,
        row=row,
        actor_user_id=actor_user_id,
        event_type="intelligence.governed_experiment_monitoring_started",
        extra={"evidence_reference_count": len(references), "external_change_only": True},
    )
    db.commit()
    db.refresh(row)
    return {"updated": True, "protocol": _serialize_protocol(db, row)}


def check_guardrails(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
    protocol_id: str,
    actor_user_id: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    row = _protocol_or_404(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=campaign_id,
        protocol_id=protocol_id,
        lock_for_update=True,
    )
    if row.status != "monitoring":
        raise HTTPException(status_code=409, detail="Safety checks are only available while results are being watched")
    checked_at = _aware(now or datetime.now(UTC))
    plan = _plan_or_404(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=campaign_id,
        plan_id=row.plan_id,
    )
    _require_matching_plan(row, plan)
    primary = _capture_metric(db, plan=plan, metric_id=plan.metric_id, at=checked_at)
    protected = [
        _capture_metric(db, plan=plan, metric_id=metric_id, at=checked_at)
        for metric_id in list(plan.guardrail_metric_ids or [])
    ]
    credits = cost_economics_service.get_customer_credit_summary(
        db, organization_id=organization_id, now=checked_at
    ).get("credits") or {}

    triggered: list[dict[str, str]] = []
    waiting_for_fresh_data = False
    primary_result = _evaluate_metric(
        dict(row.baseline_snapshot or {}),
        primary,
        started_at=row.monitoring_started_at,
        regression_code="primary_metric_regression",
        regression_label="The main result is worse than its starting point.",
    )
    triggered.extend(primary_result["triggered"])
    waiting_for_fresh_data = waiting_for_fresh_data or primary_result["waiting"]
    baseline_by_id = {
        str(item.get("metric_id") or ""): item for item in list(row.protected_baselines or [])
    }
    for item in protected:
        result = _evaluate_metric(
            baseline_by_id.get(str(item.get("metric_id") or ""), {}),
            item,
            started_at=row.monitoring_started_at,
            regression_code="protected_metric_regression",
            regression_label="A protected result is worse than its starting point.",
        )
        triggered.extend(result["triggered"])
        waiting_for_fresh_data = waiting_for_fresh_data or result["waiting"]
    if credits.get("blocked"):
        triggered.append(
            {"code": "allowance_exhausted", "message": "The account has no Insight Credits left for optional checks."}
        )
    triggered = _dedupe_rules(triggered)
    due = bool(row.observation_due_at and checked_at >= _aware(row.observation_due_at))
    if triggered:
        check_status = "stop_required"
        row.status = "stop_required"
        row.stop_reason_code = str(triggered[0]["code"])
    elif waiting_for_fresh_data:
        check_status = "waiting_for_fresh_data"
    elif due:
        check_status = "completed"
        row.status = "completed"
    else:
        check_status = "passed"

    artifact = {
        "protocol_id": row.id,
        "checked_at": checked_at.isoformat(),
        "primary_metric": primary,
        "protected_metrics": protected,
        "allowance_snapshot": credits,
        "triggered_rules": triggered,
        "status": check_status,
    }
    check = GovernedExperimentGuardrailCheck(
        protocol_id=row.id,
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=campaign_id,
        status=check_status,
        primary_metric=primary,
        protected_metrics=protected,
        allowance_snapshot=credits,
        triggered_rules=triggered,
        artifact_hash=_hash(artifact),
        checked_by_user_id=actor_user_id,
        checked_at=checked_at,
    )
    db.add(check)
    row.latest_check_summary = {
        "status": check_status,
        "checked_at": checked_at.isoformat(),
        "triggered_rules": triggered,
        "fresh_data_available": not waiting_for_fresh_data,
        "observation_due": due,
    }
    row.updated_at = checked_at
    _audit(
        db,
        row=row,
        actor_user_id=actor_user_id,
        event_type="intelligence.governed_experiment_guardrails_checked",
        extra={"check_status": check_status, "triggered_rule_codes": [item["code"] for item in triggered]},
    )
    db.commit()
    db.refresh(check)
    db.refresh(row)
    return {"check": _serialize_check(check), "protocol": _serialize_protocol(db, row)}


def stop_protocol(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
    protocol_id: str,
    actor_user_id: str,
    reason_code: str,
    note: str | None,
    now: datetime | None = None,
) -> dict[str, Any]:
    row = _protocol_or_404(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=campaign_id,
        protocol_id=protocol_id,
        lock_for_update=True,
    )
    if row.status not in {"monitoring", "stop_required"}:
        raise HTTPException(status_code=409, detail="This monitoring protocol cannot be stopped now")
    if reason_code not in STOP_REASON_CODES:
        raise HTTPException(status_code=422, detail="Choose a supported reason for stopping")
    if row.status == "stop_required" and row.stop_reason_code and reason_code != row.stop_reason_code:
        raise HTTPException(
            status_code=409,
            detail="Use the saved stop-rule reason before opening the undo steps",
        )
    resolved_at = _aware(now or datetime.now(UTC))
    row.status = "rollback_pending"
    row.stop_reason_code = reason_code
    row.stop_note = str(note or "").strip() or None
    row.stopped_by_user_id = actor_user_id
    row.stopped_at = resolved_at
    row.updated_at = resolved_at
    _audit(
        db,
        row=row,
        actor_user_id=actor_user_id,
        event_type="intelligence.governed_experiment_monitoring_stopped",
        extra={"reason_code": reason_code, "rollback_required": True},
    )
    db.commit()
    db.refresh(row)
    return {"updated": True, "protocol": _serialize_protocol(db, row)}


def verify_rollback(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
    protocol_id: str,
    actor_user_id: str,
    rollback_steps_confirmed: bool,
    evidence_references: list[str],
    now: datetime | None = None,
) -> dict[str, Any]:
    row = _protocol_or_404(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=campaign_id,
        protocol_id=protocol_id,
        lock_for_update=True,
    )
    if row.status == "rollback_verified":
        return {"updated": False, "protocol": _serialize_protocol(db, row)}
    if row.status != "rollback_pending":
        raise HTTPException(status_code=409, detail="Rollback verification is not required for this protocol")
    references = _unique_nonblank(evidence_references)
    if not rollback_steps_confirmed or not references:
        raise HTTPException(status_code=422, detail="Confirm every undo step and add verification evidence")
    resolved_at = _aware(now or datetime.now(UTC))
    row.status = "rollback_verified"
    row.rollback_evidence = references
    row.rollback_verified_by_user_id = actor_user_id
    row.rollback_verified_at = resolved_at
    row.updated_at = resolved_at
    _audit(
        db,
        row=row,
        actor_user_id=actor_user_id,
        event_type="intelligence.governed_experiment_rollback_verified",
        extra={"evidence_reference_count": len(references), "automatic_rollback": False},
    )
    db.commit()
    db.refresh(row)
    return {"updated": True, "protocol": _serialize_protocol(db, row)}


def _capture_metric(
    db: Session, *, plan: GovernedExperimentPlan, metric_id: str, at: datetime
) -> dict[str, Any]:
    return action_plan_measurement_service.capture_governed_metric_snapshot(
        db,
        tenant_id=plan.tenant_id,
        organization_id=plan.organization_id,
        campaign_id=plan.campaign_id,
        business_location_id=plan.business_location_id,
        metric_id=metric_id,
        observation_window_days=plan.observation_window_days,
        captured_at=at,
    )


def _require_available_baseline(metric: dict[str, Any], *, label: str) -> None:
    if metric.get("status") != "available" or metric.get("value") is None:
        reason = str(metric.get("insufficient_reason") or "No current measurement is available.")
        raise HTTPException(status_code=409, detail=f"A current {label} is required. {reason}")


def _require_matching_plan(
    protocol: GovernedExperimentProtocol,
    plan: GovernedExperimentPlan,
) -> None:
    if plan.status != "approved" or plan.artifact_hash != protocol.plan_artifact_hash:
        raise HTTPException(
            status_code=409,
            detail="The approved test design no longer matches this protocol",
        )


def _evaluate_metric(
    baseline: dict[str, Any],
    current: dict[str, Any],
    *,
    started_at: datetime | None,
    regression_code: str,
    regression_label: str,
) -> dict[str, Any]:
    if current.get("status") != "available" or current.get("value") is None:
        return {
            "waiting": False,
            "triggered": [{"code": "data_quality_loss", "message": "A required measurement is incomplete or unavailable."}],
        }
    comparison_keys = ("source_provider", "entity_scope", "scope_key", "measurement_window_days")
    if any(baseline.get(key) != current.get(key) for key in comparison_keys):
        return {
            "waiting": False,
            "triggered": [{"code": "data_quality_loss", "message": "A required measurement no longer matches its starting scope."}],
        }
    measured_at = _parse_datetime(current.get("measured_at"))
    if started_at is None or measured_at is None or measured_at <= _aware(started_at):
        return {"waiting": True, "triggered": []}
    before = baseline.get("value")
    after = current.get("value")
    try:
        before_value = float(before)
        after_value = float(after)
    except (TypeError, ValueError):
        return {
            "waiting": False,
            "triggered": [{"code": "data_quality_loss", "message": "A required measurement cannot be compared with its starting value."}],
        }
    direction = str(current.get("direction") or baseline.get("direction") or "")
    regressed = (
        direction == "higher_is_better" and after_value < before_value
    ) or (direction == "lower_is_better" and after_value > before_value)
    if direction not in {"higher_is_better", "lower_is_better"}:
        return {
            "waiting": False,
            "triggered": [{"code": "data_quality_loss", "message": "The measurement no longer has a governed improvement direction."}],
        }
    return {
        "waiting": False,
        "triggered": ([{"code": regression_code, "message": regression_label}] if regressed else []),
    }


def _serialize_protocol(db: Session, row: GovernedExperimentProtocol) -> dict[str, Any]:
    checks = (
        db.query(GovernedExperimentGuardrailCheck)
        .filter(
            GovernedExperimentGuardrailCheck.protocol_id == row.id,
            GovernedExperimentGuardrailCheck.tenant_id == row.tenant_id,
            GovernedExperimentGuardrailCheck.organization_id == row.organization_id,
        )
        .order_by(GovernedExperimentGuardrailCheck.checked_at.desc())
        .limit(10)
        .all()
    )
    return {
        "id": row.id,
        "plan_id": row.plan_id,
        "campaign_id": row.campaign_id,
        "business_location_id": row.business_location_id,
        "status": row.status,
        "protocol_version": row.protocol_version,
        "plan_artifact_hash": row.plan_artifact_hash,
        "protocol_hash": row.protocol_hash,
        "baseline_snapshot": dict(row.baseline_snapshot or {}),
        "protected_baselines": list(row.protected_baselines or []),
        "allowance_baseline": dict(row.allowance_baseline or {}),
        "stop_rules": list(row.stop_rules or []),
        "rollback_steps": list(row.rollback_steps or []),
        "authorization_acknowledgements": dict(row.authorization_acknowledgements or {}),
        "change_evidence": list(row.change_evidence or []),
        "latest_check_summary": dict(row.latest_check_summary or {}),
        "stop_reason_code": row.stop_reason_code,
        "stop_note": row.stop_note,
        "rollback_evidence": list(row.rollback_evidence or []),
        "authorized_at": _iso(row.authorized_at),
        "monitoring_started_at": _iso(row.monitoring_started_at),
        "observation_due_at": _iso(row.observation_due_at),
        "stopped_at": _iso(row.stopped_at),
        "rollback_verified_at": _iso(row.rollback_verified_at),
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
        "checks": [_serialize_check(item) for item in checks],
        "safety": _safety(),
    }


def _serialize_check(row: GovernedExperimentGuardrailCheck) -> dict[str, Any]:
    return {
        "id": row.id,
        "status": row.status,
        "primary_metric": dict(row.primary_metric or {}),
        "protected_metrics": list(row.protected_metrics or []),
        "allowance_snapshot": dict(row.allowance_snapshot or {}),
        "triggered_rules": list(row.triggered_rules or []),
        "artifact_hash": row.artifact_hash,
        "checked_at": _iso(row.checked_at),
    }


def _campaign_or_404(
    db: Session, *, tenant_id: str, organization_id: str, campaign_id: str
) -> Campaign:
    row = (
        db.query(Campaign)
        .filter(
            Campaign.id == campaign_id,
            Campaign.tenant_id == tenant_id,
            Campaign.organization_id == organization_id,
        )
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return row


def _plan_or_404(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
    plan_id: str,
) -> GovernedExperimentPlan:
    _campaign_or_404(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=campaign_id,
    )
    row = (
        db.query(GovernedExperimentPlan)
        .filter(
            GovernedExperimentPlan.id == plan_id,
            GovernedExperimentPlan.tenant_id == tenant_id,
            GovernedExperimentPlan.organization_id == organization_id,
            GovernedExperimentPlan.campaign_id == campaign_id,
        )
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Controlled-test plan not found")
    return row


def _protocol_or_404(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
    protocol_id: str,
    lock_for_update: bool = False,
) -> GovernedExperimentProtocol:
    _campaign_or_404(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=campaign_id,
    )
    query = (
        db.query(GovernedExperimentProtocol)
        .filter(
            GovernedExperimentProtocol.id == protocol_id,
            GovernedExperimentProtocol.tenant_id == tenant_id,
            GovernedExperimentProtocol.organization_id == organization_id,
            GovernedExperimentProtocol.campaign_id == campaign_id,
        )
    )
    if lock_for_update:
        query = query.with_for_update()
    row = query.first()
    if row is None:
        raise HTTPException(status_code=404, detail="Controlled-test monitoring protocol not found")
    return row


def _audit(
    db: Session,
    *,
    row: GovernedExperimentProtocol,
    actor_user_id: str,
    event_type: str,
    extra: dict[str, Any],
) -> None:
    write_audit_log(
        db,
        tenant_id=row.tenant_id,
        actor_user_id=actor_user_id,
        event_type=event_type,
        payload={
            "organization_id": row.organization_id,
            "campaign_id": row.campaign_id,
            "plan_id": row.plan_id,
            "protocol_id": row.id,
            "protocol_hash": row.protocol_hash,
            "status": row.status,
            "assignments_created": False,
            "publishing_enabled": False,
            "automatic_rollback": False,
            **extra,
        },
    )


def _safety() -> dict[str, bool]:
    return {
        "monitoring_only": True,
        "change_applied_by_protocol": False,
        "assignments_created": False,
        "publishing_enabled": False,
        "automatic_rollback": False,
        "legacy_experiment_connected": False,
    }


def _dedupe_rules(items: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[str] = set()
    result: list[dict[str, str]] = []
    for item in items:
        code = str(item.get("code") or "")
        if code and code not in seen:
            seen.add(code)
            result.append(item)
    return result


def _unique_nonblank(items: list[str]) -> list[str]:
    normalized = [str(item).strip() for item in items if str(item).strip()]
    if any(len(item) > 500 for item in normalized):
        raise HTTPException(status_code=422, detail="Evidence references must be 500 characters or fewer")
    return list(dict.fromkeys(normalized))


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return _aware(datetime.fromisoformat(str(value).replace("Z", "+00:00")))
    except ValueError:
        return None


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None

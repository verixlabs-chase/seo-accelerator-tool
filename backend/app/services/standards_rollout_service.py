from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
import json
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.provider_metric_contract import ProviderMetricContractVersion
from app.models.reference_library import (
    ReferenceLibraryActivation,
    ReferenceLibraryArtifact,
    ReferenceLibraryVersion,
    StandardsChangeCandidate,
)
from app.models.standards_governance import StandardsApproval, StandardsRollout
from app.models.standards_replay import StandardsReplayReport
from app.services import (
    metric_contract_service,
    performance_drift_service,
    reference_library_service,
    standards_source_service,
)
from app.services.audit_service import write_audit_log


class StandardsRolloutError(ValueError):
    pass


def decide_replay_report(
    db: Session,
    *,
    replay_report_id: str,
    decision: str,
    rationale: str,
    rollout_plan: dict[str, Any] | None,
    rollback_plan: dict[str, Any] | None,
    acknowledges_new_baseline: bool,
    actor_user_id: str,
    audit_tenant_id: str,
) -> dict[str, Any]:
    resolved_decision = decision.strip()
    if resolved_decision not in {"approved", "rejected"}:
        raise StandardsRolloutError("Choose approved or rejected.")
    resolved_rationale = rationale.strip()
    if not resolved_rationale:
        raise StandardsRolloutError("A decision rationale is required.")
    report = db.get(StandardsReplayReport, replay_report_id)
    if report is None:
        raise StandardsRolloutError("Replay report was not found.")
    if report.status not in {"passed", "changed"}:
        raise StandardsRolloutError("Only a completed replay report can be decided.")
    _assert_latest_replay(db, report)
    candidate_hash = _candidate_content_hash(db, report)

    resolved_rollout = _validated_plan(rollout_plan, "rollout") if resolved_decision == "approved" else {}
    resolved_rollback = _validated_plan(rollback_plan, "rollback") if resolved_decision == "approved" else {}
    if report.requires_new_baseline and resolved_decision == "approved" and not acknowledges_new_baseline:
        raise StandardsRolloutError(
            "Acknowledge the required new baseline before approving this replay."
        )
    previous_decision = (
        db.query(StandardsApproval)
        .filter(StandardsApproval.replay_report_id == report.id)
        .order_by(StandardsApproval.created_at.desc())
        .first()
    )
    if previous_decision is not None and previous_decision.decision == resolved_decision:
        raise StandardsRolloutError("That replay already has the same latest decision.")

    row = StandardsApproval(
        replay_report_id=report.id,
        decision=resolved_decision,
        replay_seal_digest=_replay_seal(report),
        candidate_content_hash=candidate_hash,
        rationale=resolved_rationale,
        rollout_plan_json=json.dumps(resolved_rollout, sort_keys=True),
        rollback_plan_json=json.dumps(resolved_rollback, sort_keys=True),
        acknowledges_new_baseline=bool(acknowledges_new_baseline),
        decided_by_user_id=actor_user_id,
        automatic_activation_allowed=False,
        created_at=datetime.now(UTC),
    )
    db.add(row)
    db.flush()
    write_audit_log(
        db,
        tenant_id=audit_tenant_id,
        actor_user_id=actor_user_id,
        event_type=f"standards.replay.{resolved_decision}",
        payload={
            "approval_id": row.id,
            "replay_report_id": report.id,
            "artifact_type": report.artifact_type,
            "artifact_key": report.artifact_key,
            "base_version": report.base_version,
            "candidate_version": report.candidate_version,
            "requires_new_baseline": report.requires_new_baseline,
        },
    )
    db.commit()
    db.refresh(row)
    return _approval_payload(row, report)


def create_rollout(
    db: Session,
    *,
    approval_id: str,
    rollout_mode: str,
    scheduled_for: datetime | None,
    actor_user_id: str,
    audit_tenant_id: str,
) -> dict[str, Any]:
    approval = db.get(StandardsApproval, approval_id)
    if approval is None or approval.decision != "approved":
        raise StandardsRolloutError("An approved replay decision is required.")
    report = db.get(StandardsReplayReport, approval.replay_report_id)
    if report is None:
        raise StandardsRolloutError("The approved replay report was not found.")
    _assert_latest_approval(db, approval)
    _assert_seals(db, approval, report)
    mode = rollout_mode.strip()
    if mode not in {"immediate", "scheduled"}:
        raise StandardsRolloutError("Choose an immediate or scheduled rollout.")
    now = datetime.now(UTC)
    resolved_schedule = _aware(scheduled_for or now)
    if mode == "scheduled" and resolved_schedule <= now:
        raise StandardsRolloutError("A scheduled rollout must use a future time.")
    if mode == "immediate":
        resolved_schedule = now
    existing = (
        db.query(StandardsRollout)
        .filter(
            StandardsRollout.approval_id == approval.id,
            StandardsRollout.status.in_({"scheduled", "in_progress", "completed"}),
        )
        .first()
    )
    if existing is not None:
        raise StandardsRolloutError("This approval already has an active or completed rollout.")

    row = StandardsRollout(
        approval_id=approval.id,
        artifact_type=report.artifact_type,
        artifact_key=report.artifact_key,
        base_version=report.base_version,
        candidate_version=report.candidate_version,
        rollout_mode=mode,
        status="scheduled",
        scheduled_for=resolved_schedule,
        provider_metric_contract_version_id=report.provider_metric_contract_version_id,
        reference_library_version_id=report.reference_library_version_id,
        created_by_user_id=actor_user_id,
        automatic_activation_allowed=False,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.flush()
    write_audit_log(
        db,
        tenant_id=audit_tenant_id,
        actor_user_id=actor_user_id,
        event_type="standards.rollout.scheduled",
        payload={
            "rollout_id": row.id,
            "approval_id": approval.id,
            "artifact_type": row.artifact_type,
            "artifact_key": row.artifact_key,
            "candidate_version": row.candidate_version,
            "rollout_mode": row.rollout_mode,
            "scheduled_for": row.scheduled_for.isoformat(),
        },
    )
    db.commit()
    db.refresh(row)
    return _rollout_payload(row, approval)


def execute_rollout(
    db: Session,
    *,
    rollout_id: str,
    actor_user_id: str,
    audit_tenant_id: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    row = db.get(StandardsRollout, rollout_id)
    if row is None:
        raise StandardsRolloutError("Standards rollout was not found.")
    if row.status != "scheduled":
        raise StandardsRolloutError("Only a scheduled rollout can be executed.")
    executed_at = _aware(now or datetime.now(UTC))
    if _aware(row.scheduled_for) > executed_at:
        raise StandardsRolloutError("This rollout is scheduled for a later time.")
    approval = db.get(StandardsApproval, row.approval_id)
    report = db.get(StandardsReplayReport, approval.replay_report_id) if approval else None
    if approval is None or report is None:
        raise StandardsRolloutError("The rollout approval evidence is missing.")
    _assert_latest_approval(db, approval)
    _assert_seals(db, approval, report)
    row.status = "in_progress"
    row.started_at = executed_at
    row.updated_at = executed_at
    db.commit()
    try:
        if row.artifact_type == "provider_metric_contract":
            _activate_metric_contract(db, row, report)
        elif row.artifact_type == "intelligence_lexicon":
            _activate_lexicon(db, row, report, actor_user_id)
        else:
            raise StandardsRolloutError("Unsupported rollout artifact type.")
        change = (
            db.get(StandardsChangeCandidate, report.standards_change_candidate_id)
            if report.standards_change_candidate_id
            else None
        )
        if change is not None:
            change.status = "implemented"
            change.updated_at = executed_at
        row.status = "completed"
        row.completed_at = executed_at
        row.updated_at = executed_at
        write_audit_log(
            db,
            tenant_id=audit_tenant_id,
            actor_user_id=actor_user_id,
            event_type="standards.rollout.completed",
            payload={
                "rollout_id": row.id,
                "approval_id": approval.id,
                "artifact_type": row.artifact_type,
                "artifact_key": row.artifact_key,
                "base_version": row.base_version,
                "candidate_version": row.candidate_version,
                "requires_new_baseline": report.requires_new_baseline,
            },
        )
        db.commit()
    except (StandardsRolloutError, HTTPException, RuntimeError, ValueError) as exc:
        db.rollback()
        row = db.get(StandardsRollout, rollout_id)
        if row is not None:
            row.status = "failed"
            row.failed_at = datetime.now(UTC)
            row.failure_message = str(exc)[:4000]
            row.updated_at = row.failed_at
            write_audit_log(
                db,
                tenant_id=audit_tenant_id,
                actor_user_id=actor_user_id,
                event_type="standards.rollout.failed",
                payload={"rollout_id": rollout_id, "error": str(exc)[:500]},
            )
            db.commit()
        raise StandardsRolloutError(f"Rollout failed: {exc}") from exc
    db.refresh(row)
    return _rollout_payload(row, approval)


def rollback_rollout(
    db: Session,
    *,
    rollout_id: str,
    reason: str,
    actor_user_id: str,
    audit_tenant_id: str,
) -> dict[str, Any]:
    row = db.get(StandardsRollout, rollout_id)
    if row is None:
        raise StandardsRolloutError("Standards rollout was not found.")
    if row.status != "completed":
        raise StandardsRolloutError("Only a completed rollout can be rolled back.")
    resolved_reason = reason.strip()
    if not resolved_reason:
        raise StandardsRolloutError("A rollback reason is required.")
    approval = db.get(StandardsApproval, row.approval_id)
    report = db.get(StandardsReplayReport, approval.replay_report_id) if approval else None
    if approval is None or report is None:
        raise StandardsRolloutError("The rollout approval evidence is missing.")
    if row.artifact_type == "provider_metric_contract":
        _rollback_metric_contract(db, row)
    elif row.artifact_type == "intelligence_lexicon":
        _rollback_lexicon(db, row, actor_user_id)
    else:
        raise StandardsRolloutError("Unsupported rollout artifact type.")
    rolled_back_at = datetime.now(UTC)
    row.status = "rolled_back"
    row.rolled_back_by_user_id = actor_user_id
    row.rolled_back_at = rolled_back_at
    row.rollback_reason = resolved_reason
    row.updated_at = rolled_back_at
    change = (
        db.get(StandardsChangeCandidate, report.standards_change_candidate_id)
        if report.standards_change_candidate_id
        else None
    )
    if change is not None:
        change.status = "requires_contract_update"
        change.updated_at = rolled_back_at
    write_audit_log(
        db,
        tenant_id=audit_tenant_id,
        actor_user_id=actor_user_id,
        event_type="standards.rollout.rolled_back",
        payload={
            "rollout_id": row.id,
            "artifact_type": row.artifact_type,
            "artifact_key": row.artifact_key,
            "restored_version": row.base_version,
            "removed_version": row.candidate_version,
            "reason": resolved_reason,
        },
    )
    db.commit()
    db.refresh(row)
    return _rollout_payload(row, approval)


def list_approvals(db: Session, *, limit: int = 100) -> dict[str, Any]:
    rows = db.query(StandardsApproval).order_by(StandardsApproval.created_at.desc()).limit(limit).all()
    items = []
    for row in rows:
        report = db.get(StandardsReplayReport, row.replay_report_id)
        if report is not None:
            items.append(_approval_payload(row, report))
    return {"items": items, "returned": len(items)}


def list_rollouts(db: Session, *, limit: int = 100) -> dict[str, Any]:
    rows = db.query(StandardsRollout).order_by(StandardsRollout.created_at.desc()).limit(limit).all()
    items = []
    for row in rows:
        approval = db.get(StandardsApproval, row.approval_id)
        if approval is not None:
            items.append(_rollout_payload(row, approval))
    return {"items": items, "returned": len(items)}


def standards_status(db: Session, *, tenant_id: str | None) -> dict[str, Any]:
    standards_source_service.ensure_default_sources(db)
    metric_contract_service.ensure_default_contracts(db)
    source_status = standards_source_service.list_source_status(db)
    healthy_sources = sum(
        item["last_checked_at"] is not None and item["last_error_code"] is None
        for item in source_status["items"]
    )
    sources_needing_attention = len(source_status["items"]) - healthy_sources
    changes = standards_source_service.list_change_candidates(db, limit=25)
    replays = (
        db.query(StandardsReplayReport)
        .order_by(StandardsReplayReport.created_at.desc())
        .limit(25)
        .all()
    )
    active_contracts = (
        db.query(ProviderMetricContractVersion)
        .filter(ProviderMetricContractVersion.is_active.is_(True))
        .all()
    )
    contract_candidates = (
        db.query(ProviderMetricContractVersion)
        .filter(ProviderMetricContractVersion.lifecycle_status == "candidate")
        .all()
    )
    active_lexicon = None
    if tenant_id:
        active_lexicon = (
            db.query(ReferenceLibraryVersion)
            .filter(
                ReferenceLibraryVersion.tenant_id == tenant_id,
                ReferenceLibraryVersion.status == "active",
            )
            .order_by(ReferenceLibraryVersion.updated_at.desc())
            .first()
        )
    audit_rows = (
        db.query(AuditLog)
        .filter(AuditLog.event_type.like("standards.%"))
        .order_by(AuditLog.created_at.desc())
        .limit(50)
        .all()
    )
    drift_events = performance_drift_service.list_drift_events(db, limit=25)["items"]
    return {
        "summary": {
            "healthy_sources": healthy_sources,
            "sources_needing_attention": sources_needing_attention,
            "changes_needing_review": sum(
                item["status"] in {"needs_review", "requires_contract_update"}
                for item in changes["items"]
            ),
            "candidate_contracts": len(contract_candidates),
            "replays_waiting_for_decision": _replays_waiting_for_decision(db, replays),
            "scheduled_rollouts": db.query(StandardsRollout)
            .filter(StandardsRollout.status == "scheduled")
            .count(),
            "performance_drift_events_needing_review": sum(
                item["status"] in {"needs_review", "investigating"}
                for item in drift_events
            ),
        },
        "sources": source_status["items"],
        "active_versions": {
            "lexicon": active_lexicon.version if active_lexicon else None,
            "lexicon_scope_tenant_id": tenant_id,
            "metric_contract_count": len(active_contracts),
            "metric_contract_versions": sorted(
                {row.version for row in active_contracts}
            ),
        },
        "changes": changes["items"],
        "candidate_contracts": [_contract_summary(row) for row in contract_candidates],
        "replays": [_replay_summary(row) for row in replays],
        "approvals": list_approvals(db, limit=25)["items"],
        "rollouts": list_rollouts(db, limit=25)["items"],
        "performance_drift_events": drift_events,
        "audit_history": [_audit_payload(row) for row in audit_rows],
        "automatic_activation_allowed": False,
    }


def _activate_metric_contract(
    db: Session,
    rollout: StandardsRollout,
    report: StandardsReplayReport,
) -> None:
    candidate = db.get(ProviderMetricContractVersion, rollout.provider_metric_contract_version_id)
    if candidate is None or candidate.lifecycle_status != "candidate" or candidate.is_active:
        raise StandardsRolloutError("The candidate metric contract is no longer rollout-ready.")
    previous = db.get(ProviderMetricContractVersion, candidate.supersedes_version_id)
    if previous is None or not previous.is_active or previous.version != report.base_version:
        raise StandardsRolloutError("The active metric contract changed after replay; run replay again.")
    rollout.previous_provider_metric_contract_version_id = previous.id
    previous.is_active = False
    previous.lifecycle_status = "retired"
    candidate.is_active = True
    candidate.lifecycle_status = "active"


def _activate_lexicon(
    db: Session,
    rollout: StandardsRollout,
    report: StandardsReplayReport,
    actor_user_id: str,
) -> None:
    candidate = db.get(ReferenceLibraryVersion, rollout.reference_library_version_id)
    if candidate is None or candidate.status != "validated":
        raise StandardsRolloutError("The candidate lexicon is no longer rollout-ready.")
    previous = (
        db.query(ReferenceLibraryVersion)
        .filter(
            ReferenceLibraryVersion.tenant_id == candidate.tenant_id,
            ReferenceLibraryVersion.status == "active",
        )
        .first()
    )
    if previous is None or previous.version != report.base_version:
        raise StandardsRolloutError("The active lexicon changed after replay; run replay again.")
    rollout.previous_reference_library_version_id = previous.id
    reference_library_service.activate_version(
        db,
        tenant_id=candidate.tenant_id,
        actor_user_id=actor_user_id,
        version=candidate.version,
        reason="Approved standards rollout",
        standards_rollout_id=rollout.id,
        commit=False,
    )


def _rollback_metric_contract(db: Session, rollout: StandardsRollout) -> None:
    current = db.get(ProviderMetricContractVersion, rollout.provider_metric_contract_version_id)
    previous = db.get(
        ProviderMetricContractVersion,
        rollout.previous_provider_metric_contract_version_id,
    )
    if current is None or previous is None or not current.is_active:
        raise StandardsRolloutError("The active contract no longer matches this rollout.")
    current.is_active = False
    current.lifecycle_status = "retired"
    previous.is_active = True
    previous.lifecycle_status = "active"


def _rollback_lexicon(db: Session, rollout: StandardsRollout, actor_user_id: str) -> None:
    current = db.get(ReferenceLibraryVersion, rollout.reference_library_version_id)
    previous = db.get(ReferenceLibraryVersion, rollout.previous_reference_library_version_id)
    if current is None or previous is None or current.status != "active":
        raise StandardsRolloutError("The active lexicon no longer matches this rollout.")
    current.status = "validated"
    current.updated_at = datetime.now(UTC)
    previous.status = "active"
    previous.updated_at = datetime.now(UTC)
    db.add(
        ReferenceLibraryActivation(
            tenant_id=previous.tenant_id,
            reference_library_version_id=previous.id,
            activated_by=actor_user_id,
            rollback_from_version=current.version,
            activation_status="active",
            created_at=datetime.now(UTC),
        )
    )


def _assert_latest_replay(db: Session, report: StandardsReplayReport) -> None:
    query = db.query(StandardsReplayReport).filter(
        StandardsReplayReport.artifact_type == report.artifact_type,
        StandardsReplayReport.artifact_key == report.artifact_key,
    )
    if report.provider_metric_contract_version_id:
        query = query.filter(
            StandardsReplayReport.provider_metric_contract_version_id
            == report.provider_metric_contract_version_id
        )
    if report.reference_library_version_id:
        query = query.filter(
            StandardsReplayReport.reference_library_version_id == report.reference_library_version_id
        )
    latest = query.order_by(StandardsReplayReport.created_at.desc()).first()
    if latest is None or latest.id != report.id:
        raise StandardsRolloutError("Approve the latest replay report for this candidate.")


def _assert_latest_approval(db: Session, approval: StandardsApproval) -> None:
    latest = (
        db.query(StandardsApproval)
        .filter(StandardsApproval.replay_report_id == approval.replay_report_id)
        .order_by(StandardsApproval.created_at.desc())
        .first()
    )
    if latest is None or latest.id != approval.id or latest.decision != "approved":
        raise StandardsRolloutError("This is no longer the latest approved decision.")


def _assert_seals(
    db: Session,
    approval: StandardsApproval,
    report: StandardsReplayReport,
) -> None:
    if approval.replay_seal_digest != _replay_seal(report):
        raise StandardsRolloutError("The replay report changed after approval.")
    if approval.candidate_content_hash != _candidate_content_hash(db, report):
        raise StandardsRolloutError("The candidate changed after approval; run replay again.")


def _candidate_content_hash(db: Session, report: StandardsReplayReport) -> str:
    if report.artifact_type == "provider_metric_contract":
        row = db.get(ProviderMetricContractVersion, report.provider_metric_contract_version_id)
        if row is None:
            raise StandardsRolloutError("Candidate metric contract was not found.")
        return row.content_hash
    if report.artifact_type == "intelligence_lexicon":
        artifact = (
            db.query(ReferenceLibraryArtifact)
            .filter(
                ReferenceLibraryArtifact.reference_library_version_id
                == report.reference_library_version_id,
                ReferenceLibraryArtifact.artifact_type == "intelligence_lexicon",
            )
            .one_or_none()
        )
        if artifact is None:
            raise StandardsRolloutError("Candidate lexicon artifact was not found.")
        return artifact.artifact_sha256
    raise StandardsRolloutError("Unsupported replay artifact type.")


def _replay_seal(report: StandardsReplayReport) -> str:
    return _stable_hash(
        {
            "id": report.id,
            "artifact_type": report.artifact_type,
            "artifact_key": report.artifact_key,
            "base_version": report.base_version,
            "candidate_version": report.candidate_version,
            "sample_digest": report.sample_digest,
            "status": report.status,
            "definition_diff_json": report.definition_diff_json,
            "impact_report_json": report.impact_report_json,
            "replay_results_json": report.replay_results_json,
            "requires_new_baseline": report.requires_new_baseline,
        }
    )


def _validated_plan(value: dict[str, Any] | None, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise StandardsRolloutError(f"A {label} plan is required.")
    summary = str(value.get("summary") or "").strip()
    steps = value.get("steps")
    if not summary or not isinstance(steps, list) or not steps:
        raise StandardsRolloutError(f"The {label} plan needs a summary and at least one step.")
    clean_steps = [str(step).strip() for step in steps if str(step).strip()]
    if not clean_steps:
        raise StandardsRolloutError(f"The {label} plan needs at least one usable step.")
    return {
        "summary": summary[:1000],
        "steps": clean_steps[:20],
        "monitoring_window_hours": max(1, min(int(value.get("monitoring_window_hours") or 24), 720)),
    }


def _approval_payload(row: StandardsApproval, report: StandardsReplayReport) -> dict[str, Any]:
    return {
        "id": row.id,
        "replay_report_id": row.replay_report_id,
        "artifact_type": report.artifact_type,
        "artifact_key": report.artifact_key,
        "base_version": report.base_version,
        "candidate_version": report.candidate_version,
        "decision": row.decision,
        "rationale": row.rationale,
        "rollout_plan": _json_object(row.rollout_plan_json),
        "rollback_plan": _json_object(row.rollback_plan_json),
        "acknowledges_new_baseline": row.acknowledges_new_baseline,
        "decided_by_user_id": row.decided_by_user_id,
        "automatic_activation_allowed": False,
        "created_at": row.created_at,
    }


def _rollout_payload(row: StandardsRollout, approval: StandardsApproval) -> dict[str, Any]:
    return {
        "id": row.id,
        "approval_id": row.approval_id,
        "artifact_type": row.artifact_type,
        "artifact_key": row.artifact_key,
        "base_version": row.base_version,
        "candidate_version": row.candidate_version,
        "rollout_mode": row.rollout_mode,
        "status": row.status,
        "scheduled_for": row.scheduled_for,
        "started_at": row.started_at,
        "completed_at": row.completed_at,
        "failed_at": row.failed_at,
        "failure_message": row.failure_message,
        "rolled_back_at": row.rolled_back_at,
        "rollback_reason": row.rollback_reason,
        "rollout_plan": _json_object(approval.rollout_plan_json),
        "rollback_plan": _json_object(approval.rollback_plan_json),
        "automatic_activation_allowed": False,
        "created_by_user_id": row.created_by_user_id,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _contract_summary(row: ProviderMetricContractVersion) -> dict[str, Any]:
    return {
        "id": row.id,
        "contract_id": row.contract_id,
        "version": row.version,
        "base_version_id": row.supersedes_version_id,
        "change_candidate_id": row.standards_change_candidate_id,
        "proposed_at": row.proposed_at,
        "is_active": row.is_active,
    }


def _replay_summary(row: StandardsReplayReport) -> dict[str, Any]:
    return {
        "id": row.id,
        "artifact_type": row.artifact_type,
        "artifact_key": row.artifact_key,
        "base_version": row.base_version,
        "candidate_version": row.candidate_version,
        "status": row.status,
        "changed_diagnoses": row.changed_diagnoses,
        "changed_actions": row.changed_actions,
        "changed_forecasts": row.changed_forecasts,
        "changed_results": row.changed_results,
        "invalidated_comparisons": row.invalidated_comparisons,
        "requires_new_baseline": row.requires_new_baseline,
        "created_at": row.created_at,
    }


def _audit_payload(row: AuditLog) -> dict[str, Any]:
    return {
        "id": row.id,
        "event_type": row.event_type,
        "actor_user_id": row.actor_user_id,
        "payload": _json_object(row.payload_json),
        "created_at": row.created_at,
    }


def _replays_waiting_for_decision(
    db: Session,
    replays: list[StandardsReplayReport],
) -> int:
    count = 0
    for report in replays:
        latest = (
            db.query(StandardsApproval)
            .filter(StandardsApproval.replay_report_id == report.id)
            .order_by(StandardsApproval.created_at.desc())
            .first()
        )
        if latest is None:
            count += 1
    return count


def _json_object(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _stable_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(encoded.encode("utf-8")).hexdigest()


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)

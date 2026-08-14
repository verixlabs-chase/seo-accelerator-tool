from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.campaign import Campaign
from app.models.governed_experiment import GovernedExperimentPlan
from app.services import outcome_learning_service
from app.services.audit_service import write_audit_log


DESIGN_VERSION = "1.0"
DESIGN_LABELS = {
    "content_split": "Compare two approved page versions",
    "staggered_rollout": "Start with a small group, then expand",
    "holdout_comparison": "Compare changed and unchanged groups",
}
DEFAULT_STOP_RULES = [
    {
        "code": "safety_issue",
        "label": "Stop if the website or listing has a safety problem",
        "required": True,
    },
    {
        "code": "primary_metric_regression",
        "label": "Stop if the main result gets worse than its starting point",
        "required": True,
    },
    {
        "code": "data_quality_loss",
        "label": "Stop if the measurement becomes incomplete or no longer matches",
        "required": True,
    },
    {
        "code": "allowance_exhausted",
        "label": "Stop before the account uses more Insight Credits than allowed",
        "required": True,
    },
]


def list_plans(
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
        db.query(GovernedExperimentPlan)
        .filter(
            GovernedExperimentPlan.tenant_id == tenant_id,
            GovernedExperimentPlan.organization_id == organization_id,
            GovernedExperimentPlan.campaign_id == campaign_id,
        )
        .order_by(
            GovernedExperimentPlan.created_at.desc(),
            GovernedExperimentPlan.id.desc(),
        )
        .all()
    )
    learning = _learning_view(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=campaign_id,
    )
    return {
        "items": [
            _serialize_plan(
                row,
                eligibility_override=_eligibility(
                    _find_group(
                        learning,
                        action_id=row.action_id,
                        metric_id=row.metric_id,
                        measurement_contract_version=row.measurement_contract_version,
                    )
                ),
            )
            for row in rows
        ],
        "count": len(rows),
        "safety": _safety(),
    }


def create_plan(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
    actor_user_id: str,
    action_id: str,
    metric_id: str,
    measurement_contract_version: str,
    hypothesis: str,
    design_type: str,
    minimum_sample_size: int,
    observation_window_days: int,
    guardrail_metric_ids: list[str] | None,
    rollback_steps: list[str],
) -> dict[str, Any]:
    campaign = _campaign_or_404(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=campaign_id,
    )
    learning = _learning_view(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=campaign_id,
    )
    group = _find_group(
        learning,
        action_id=action_id,
        metric_id=metric_id,
        measurement_contract_version=measurement_contract_version,
    )
    if group is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Finish and review at least one matching measured result before saving "
                "a controlled-test plan"
            ),
        )

    normalized_hypothesis = hypothesis.strip()
    normalized_guardrails = _unique_nonblank(guardrail_metric_ids or [])
    normalized_guardrails = [
        item for item in normalized_guardrails if item != metric_id
    ]
    normalized_rollback = _unique_nonblank(rollback_steps)
    if not normalized_rollback:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Add at least one step that explains how to undo the test",
        )

    eligibility = _eligibility(group)
    plan_artifact = {
        "action_id": action_id,
        "metric_id": metric_id,
        "measurement_contract_version": measurement_contract_version,
        "hypothesis": normalized_hypothesis,
        "design_type": design_type,
        "minimum_sample_size": minimum_sample_size,
        "observation_window_days": observation_window_days,
        "guardrail_metric_ids": normalized_guardrails,
        "rollback_steps": normalized_rollback,
        "stop_rules": DEFAULT_STOP_RULES,
        "design_version": DESIGN_VERSION,
    }
    artifact_hash = _hash(plan_artifact)
    idempotency_key = _hash(
        {
            "tenant_id": tenant_id,
            "campaign_id": campaign_id,
            "artifact_hash": artifact_hash,
        }
    )
    existing = (
        db.query(GovernedExperimentPlan)
        .filter(
            GovernedExperimentPlan.tenant_id == tenant_id,
            GovernedExperimentPlan.idempotency_key == idempotency_key,
        )
        .first()
    )
    if existing is not None:
        return {"created": False, "plan": _serialize_plan(existing)}

    row = GovernedExperimentPlan(
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=campaign_id,
        business_location_id=campaign.business_location_id,
        action_id=action_id,
        metric_id=metric_id,
        measurement_contract_version=measurement_contract_version,
        hypothesis=normalized_hypothesis,
        design_type=design_type,
        status="draft",
        minimum_sample_size=minimum_sample_size,
        observation_window_days=observation_window_days,
        guardrail_metric_ids=normalized_guardrails,
        eligibility_snapshot=eligibility,
        stop_rules=[dict(item) for item in DEFAULT_STOP_RULES],
        rollback_steps=normalized_rollback,
        design_version=DESIGN_VERSION,
        artifact_hash=artifact_hash,
        idempotency_key=idempotency_key,
        created_by_user_id=actor_user_id,
    )
    db.add(row)
    db.flush()
    write_audit_log(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        event_type="intelligence.governed_experiment_plan_created",
        payload={
            "campaign_id": campaign_id,
            "plan_id": row.id,
            "action_id": action_id,
            "metric_id": metric_id,
            "design_type": design_type,
            "artifact_hash": artifact_hash,
            "eligible_for_design_approval": eligibility["eligible"],
            "launch_enabled": False,
            "assignments_created": False,
        },
    )
    db.commit()
    db.refresh(row)
    return {"created": True, "plan": _serialize_plan(row)}


def review_plan(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
    plan_id: str,
    actor_user_id: str,
    decision: str,
    note: str | None,
) -> dict[str, Any]:
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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Controlled-test plan not found",
        )

    normalized_note = str(note or "").strip() or None
    if row.status == decision:
        return {"updated": False, "plan": _serialize_plan(row)}
    if row.status != "draft":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This plan has already received a final owner decision",
        )
    if decision in {"rejected", "cancelled"} and not normalized_note:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Add a short reason before rejecting or cancelling this plan",
        )

    if decision == "approved":
        learning = _learning_view(
            db,
            tenant_id=tenant_id,
            organization_id=organization_id,
            campaign_id=campaign_id,
        )
        group = _find_group(
            learning,
            action_id=row.action_id,
            metric_id=row.metric_id,
            measurement_contract_version=row.measurement_contract_version,
        )
        eligibility = _eligibility(group)
        if not eligibility["eligible"]:
            examples_needed = eligibility["examples_needed"]
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Review {examples_needed} more matching result"
                    f"{'s' if examples_needed != 1 else ''} before approving this test design"
                ),
            )
        row.eligibility_snapshot = eligibility

    now = datetime.now(UTC)
    row.status = decision
    row.reviewed_by_user_id = actor_user_id
    row.reviewed_at = now
    row.review_note = normalized_note
    row.updated_at = now
    write_audit_log(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        event_type="intelligence.governed_experiment_plan_reviewed",
        payload={
            "campaign_id": campaign_id,
            "plan_id": row.id,
            "decision": decision,
            "review_note_provided": normalized_note is not None,
            "launch_enabled": False,
            "assignments_created": False,
            "publishing_enabled": False,
        },
    )
    db.commit()
    db.refresh(row)
    return {"updated": True, "plan": _serialize_plan(row)}


def _campaign_or_404(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
) -> Campaign:
    campaign = (
        db.query(Campaign)
        .filter(
            Campaign.id == campaign_id,
            Campaign.tenant_id == tenant_id,
            Campaign.organization_id == organization_id,
        )
        .first()
    )
    if campaign is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found",
        )
    return campaign


def _learning_view(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
) -> dict[str, Any]:
    return outcome_learning_service.get_campaign_outcome_learning(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=campaign_id,
        limit=200,
    )


def _find_group(
    learning: dict[str, Any],
    *,
    action_id: str,
    metric_id: str,
    measurement_contract_version: str,
) -> dict[str, Any] | None:
    return next(
        (
            group
            for group in learning.get("groups", [])
            if group.get("action_id") == action_id
            and group.get("metric_id") == metric_id
            and group.get("measurement_contract_version")
            == measurement_contract_version
        ),
        None,
    )


def _eligibility(group: dict[str, Any] | None) -> dict[str, Any]:
    required = outcome_learning_service.MINIMUM_COMPARABLE_OUTCOMES
    included = int(group.get("included_count", 0) or 0) if group else 0
    examples_needed = max(0, required - included)
    matching_group_found = group is not None
    review_ready = bool(group and group.get("review_ready"))
    blockers: list[dict[str, str]] = []
    if not matching_group_found:
        blockers.append(
            {
                "code": "no_matching_results",
                "message": "No matching measured results are available yet.",
            }
        )
    elif not review_ready:
        blockers.append(
            {
                "code": "needs_more_owner_reviewed_results",
                "message": (
                    f"Review {examples_needed} more matching result"
                    f"{'s' if examples_needed != 1 else ''}."
                ),
            }
        )
    return {
        "eligible": bool(matching_group_found and review_ready),
        "matching_group_found": matching_group_found,
        "review_ready": review_ready,
        "matching_result_count": included,
        "required_prior_results": required,
        "examples_needed": examples_needed,
        "blockers": blockers,
        "captured_at": datetime.now(UTC).isoformat(),
    }


def _serialize_plan(
    row: GovernedExperimentPlan,
    *,
    eligibility_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": row.id,
        "campaign_id": row.campaign_id,
        "business_location_id": row.business_location_id,
        "action_id": row.action_id,
        "metric_id": row.metric_id,
        "measurement_contract_version": row.measurement_contract_version,
        "hypothesis": row.hypothesis,
        "design_type": row.design_type,
        "design_label": DESIGN_LABELS.get(row.design_type, row.design_type),
        "status": row.status,
        "minimum_sample_size": row.minimum_sample_size,
        "observation_window_days": row.observation_window_days,
        "guardrail_metric_ids": list(row.guardrail_metric_ids or []),
        "eligibility": eligibility_override or dict(row.eligibility_snapshot or {}),
        "stop_rules": list(row.stop_rules or []),
        "rollback_steps": list(row.rollback_steps or []),
        "design_version": row.design_version,
        "artifact_hash": row.artifact_hash,
        "created_by_user_id": row.created_by_user_id,
        "reviewed_by_user_id": row.reviewed_by_user_id,
        "reviewed_at": _iso(row.reviewed_at),
        "review_note": row.review_note,
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
        "safety": _safety(),
    }


def _safety() -> dict[str, bool]:
    return {
        "approval_is_launch": False,
        "launch_enabled": False,
        "assignments_created": False,
        "publishing_enabled": False,
        "automatic_policy_changes_enabled": False,
        "legacy_experiment_connected": False,
    }


def _unique_nonblank(items: list[str]) -> list[str]:
    return list(dict.fromkeys(str(item).strip() for item in items if str(item).strip()))


def _hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.action_plan import ActionPlanOccurrence, ActionPlanStep
from app.models.intelligence import StrategyRecommendation
from app.models.recommendation_execution import RecommendationExecution
from app.services import (
    action_plan_forecast_service,
    action_plan_measurement_service,
    job_service,
)
from app.services.audit_service import write_audit_log
from app.services.wordpress_automation_policy_service import (
    is_managed_wordpress_execution,
)


FOLLOW_UP_CONTRACT_VERSION = "wordpress-post-change-measurement-v1"
FOLLOW_UP_JOB_TYPE = "wordpress.post_change_measurement"
SYSTEM_COMPLETION_EVIDENCE = (
    "InsightOS applied the approved WordPress change and confirmed it on the public page."
)
logger = logging.getLogger("lsos.wordpress.post_change_measurement")


def prepare_managed_wordpress_measurement(
    db: Session,
    *,
    execution: RecommendationExecution,
    recommendation: StrategyRecommendation,
    prepared_at: datetime | None = None,
) -> dict[str, Any]:
    """Capture the governed baseline before a managed WordPress mutation runs."""
    if not is_managed_wordpress_execution(execution):
        return {"required": False, "status": "not_required"}

    payload = _load_payload(execution.execution_payload)
    existing = payload.get("post_change_measurement")
    if isinstance(existing, dict) and existing.get("occurrence_id"):
        return dict(existing)

    # Imported locally because intelligence_service owns occurrence materialization
    # and imports the execution engine for its customer-triggered execution path.
    from app.services import intelligence_service

    resolved_at = prepared_at or datetime.now(UTC)
    plans = intelligence_service.build_recommendation_action_plans(
        db,
        tenant_id=recommendation.tenant_id,
        recommendations=[recommendation],
    )
    plan = plans.get(recommendation.id)
    if plan is None:
        result = {
            "required": True,
            "status": "unavailable",
            "contract_version": FOLLOW_UP_CONTRACT_VERSION,
            "reason_code": "wordpress_measurement_action_not_mapped",
            "message": "This website action does not have a governed result measurement yet.",
        }
        _save_tracking_payload(execution, payload, result)
        return result

    work_items = intelligence_service.ensure_action_plan_occurrences(
        db,
        tenant_id=recommendation.tenant_id,
        campaign_id=recommendation.campaign_id,
        recommendations=[recommendation],
        action_plans=plans,
        now=resolved_at,
        commit=False,
    )
    work_item = work_items.get(recommendation.id)
    occurrence_id = str((work_item or {}).get("id") or "")
    occurrence = db.get(ActionPlanOccurrence, occurrence_id) if occurrence_id else None
    if occurrence is None:
        result = {
            "required": True,
            "status": "unavailable",
            "contract_version": FOLLOW_UP_CONTRACT_VERSION,
            "reason_code": "wordpress_measurement_occurrence_missing",
            "message": "InsightOS could not create the matching result measurement.",
        }
        _save_tracking_payload(execution, payload, result)
        return result

    measurement = action_plan_measurement_service.capture_action_plan_baseline(
        db,
        occurrence=occurrence,
        captured_at=resolved_at,
    )
    if action_plan_forecast_service.get_action_plan_forecast(
        db,
        occurrence_id=occurrence.id,
    ) is None:
        action_plan_forecast_service.ensure_action_plan_forecast(
            db,
            occurrence=occurrence,
            measurement=measurement,
            generated_at=resolved_at,
        )

    result = {
        "required": True,
        "status": "baseline_captured",
        "contract_version": FOLLOW_UP_CONTRACT_VERSION,
        "occurrence_id": occurrence.id,
        "measurement_id": measurement.id,
        "baseline_captured_at": measurement.baseline_captured_at.isoformat(),
        "success_metric_ids": list(measurement.success_metric_ids or []),
        "primary_metric_id": str(
            (measurement.measurement_contract or {}).get("primary_metric_id") or ""
        ),
        "measurement_track": str(
            (measurement.measurement_contract or {}).get("track") or "website"
        ),
    }
    _save_tracking_payload(execution, payload, result)
    return result


def schedule_managed_wordpress_follow_up(
    db: Session,
    *,
    execution: RecommendationExecution,
    result_summary: dict[str, Any],
    completed_at: datetime | None = None,
) -> dict[str, Any]:
    """Record verified completion and create one idempotent future measurement job."""
    if not is_managed_wordpress_execution(execution):
        return {"required": False, "status": "not_required"}

    payload = _load_payload(execution.execution_payload)
    tracking = payload.get("post_change_measurement")
    if not isinstance(tracking, dict) or not tracking.get("occurrence_id"):
        return {
            "required": True,
            "status": "unavailable",
            "contract_version": FOLLOW_UP_CONTRACT_VERSION,
            "reason_code": "wordpress_measurement_baseline_missing",
            "message": "The website change completed, but no comparable starting measurement was available.",
        }

    occurrence = db.get(ActionPlanOccurrence, str(tracking["occurrence_id"]))
    if occurrence is None or occurrence.campaign_id != execution.campaign_id:
        return {
            "required": True,
            "status": "unavailable",
            "contract_version": FOLLOW_UP_CONTRACT_VERSION,
            "reason_code": "wordpress_measurement_occurrence_missing",
            "message": "The website change completed, but its saved result measurement is unavailable.",
        }

    resolved_at = completed_at or execution.executed_at or datetime.now(UTC)
    steps = (
        db.query(ActionPlanStep)
        .filter(
            ActionPlanStep.tenant_id == occurrence.tenant_id,
            ActionPlanStep.organization_id == occurrence.organization_id,
            ActionPlanStep.occurrence_id == occurrence.id,
        )
        .order_by(ActionPlanStep.position.asc(), ActionPlanStep.id.asc())
        .all()
    )
    for step in steps:
        if not step.required:
            continue
        step.status = "done"
        step.blocker_reason = None
        step.completed_by_user_id = None
        step.completed_at = resolved_at
        step.updated_at = resolved_at
        step.evidence = list(
            dict.fromkeys([*(str(item) for item in (step.evidence or [])), SYSTEM_COMPLETION_EVIDENCE])
        )

    occurrence.status = "waiting_for_results"
    occurrence.completed_at = resolved_at
    occurrence.updated_at = resolved_at
    measurement = action_plan_measurement_service.mark_action_plan_work_completed(
        db,
        occurrence=occurrence,
        steps=steps,
        completed_at=resolved_at,
    )
    affected_urls = _affected_urls(result_summary)
    contract = dict(measurement.measurement_contract or {})
    contract["managed_wordpress_execution"] = {
        "contract_version": FOLLOW_UP_CONTRACT_VERSION,
        "execution_id": execution.id,
        "recommendation_id": execution.recommendation_id,
        "completed_at": resolved_at.isoformat(),
        "public_verification_passed": True,
        "affected_urls": affected_urls,
        "causal_claim": False,
    }
    measurement.measurement_contract = contract

    due_at = measurement.observation_due_at or resolved_at
    job = job_service.create_job(
        db,
        tenant_id=measurement.tenant_id,
        job_type=FOLLOW_UP_JOB_TYPE,
        entity_type="action_plan_measurement",
        entity_id=measurement.id,
        idempotency_key=(
            f"wordpress-post-change-measurement:{measurement.id}:{due_at.isoformat()}"
        ),
        payload={
            "tenant_id": measurement.tenant_id,
            "organization_id": measurement.organization_id,
            "campaign_id": measurement.campaign_id,
            "business_location_id": measurement.business_location_id,
            "execution_id": execution.id,
            "occurrence_id": occurrence.id,
            "measurement_id": measurement.id,
            "due_at": due_at.isoformat(),
            "contract_version": FOLLOW_UP_CONTRACT_VERSION,
        },
        available_at=due_at,
        max_retries=2,
    )
    contract = dict(measurement.measurement_contract or {})
    contract["follow_up_schedule"] = {
        "job_id": job.id,
        "job_type": FOLLOW_UP_JOB_TYPE,
        "scheduled_for": due_at.isoformat(),
        "uses_governed_connected_data": True,
        "duplicate_provider_checks": False,
    }
    measurement.measurement_contract = contract
    db.flush()
    write_audit_log(
        db,
        tenant_id=measurement.tenant_id,
        actor_user_id="InsightOS measurement scheduler",
        event_type="wordpress.post_change_measurement.scheduled",
        payload={
            "campaign_id": measurement.campaign_id,
            "execution_id": execution.id,
            "occurrence_id": occurrence.id,
            "measurement_id": measurement.id,
            "job_id": job.id,
            "scheduled_for": due_at.isoformat(),
            "success_metric_ids": list(measurement.success_metric_ids or []),
            "causal_claim": False,
        },
    )
    db.flush()
    return {
        "required": True,
        "status": "scheduled",
        "contract_version": FOLLOW_UP_CONTRACT_VERSION,
        "occurrence_id": occurrence.id,
        "measurement_id": measurement.id,
        "job_id": job.id,
        "scheduled_for": due_at.isoformat(),
        "success_metric_ids": list(measurement.success_metric_ids or []),
        "causal_claim": False,
        "message": "InsightOS will check the saved result after the required waiting period.",
    }


def _save_tracking_payload(
    execution: RecommendationExecution,
    payload: dict[str, Any],
    tracking: dict[str, Any],
) -> None:
    payload["post_change_measurement"] = tracking
    execution.execution_payload = json.dumps(payload, sort_keys=True)


def _affected_urls(result_summary: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for mutation in result_summary.get("mutation_results") or []:
        if not isinstance(mutation, dict):
            continue
        value = str(mutation.get("target_url") or "").strip()
        if value:
            values.append(value)
    verification = result_summary.get("public_verification")
    if isinstance(verification, dict):
        for item in verification.get("results") or []:
            if not isinstance(item, dict):
                continue
            value = str(item.get("target_url") or item.get("url") or "").strip()
            if value:
                values.append(value)
    return list(dict.fromkeys(values))


def _load_payload(raw: str | None) -> dict[str, Any]:
    try:
        value = json.loads(raw or "{}")
    except (json.JSONDecodeError, TypeError):
        logger.warning("managed WordPress execution payload is not valid JSON")
        return {}
    return value if isinstance(value, dict) else {}

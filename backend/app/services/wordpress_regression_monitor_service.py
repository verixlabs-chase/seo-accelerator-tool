from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.action_plan import ActionPlanMeasurement
from app.models.recommendation_execution import RecommendationExecution
from app.services.audit_service import write_audit_log
from app.services.wordpress_automation_policy_service import (
    get_wordpress_automation_policy,
    is_managed_wordpress_execution,
    pause_wordpress_automation_policy,
)


REGRESSION_PAUSE_THRESHOLD = 2
REGRESSION_HISTORY_LIMIT = 12


def evaluate_wordpress_regression_pause(
    db: Session,
    *,
    measurement: ActionPlanMeasurement,
) -> dict[str, Any]:
    base = {
        "evaluated": True,
        "threshold": REGRESSION_PAUSE_THRESHOLD,
        "consecutive_regressions": 0,
        "measurement_ids": [],
        "metric_ids": [],
        "causal_claim": False,
        "note": (
            "These measurements were observed after managed website work. "
            "They do not prove that the website changes caused the movement."
        ),
    }
    if (
        measurement.measurement_status != "measured"
        or measurement.result_classification != "worse"
    ):
        return {**base, "status": "not_applicable"}

    policy = get_wordpress_automation_policy(
        db,
        campaign_id=measurement.campaign_id,
    )
    if policy is None or not policy.automation_enabled:
        return {**base, "status": "policy_off"}
    if policy.emergency_stop:
        return {
            **base,
            "status": "already_paused",
            "pause_reason_code": policy.paused_reason_code,
        }

    recent = (
        db.query(ActionPlanMeasurement)
        .filter(
            ActionPlanMeasurement.tenant_id == measurement.tenant_id,
            ActionPlanMeasurement.organization_id == measurement.organization_id,
            ActionPlanMeasurement.campaign_id == measurement.campaign_id,
            ActionPlanMeasurement.measurement_status == "measured",
        )
        .order_by(
            ActionPlanMeasurement.outcome_measured_at.desc(),
            ActionPlanMeasurement.id.desc(),
        )
        .limit(REGRESSION_HISTORY_LIMIT)
        .all()
    )
    regressions: list[tuple[ActionPlanMeasurement, RecommendationExecution]] = []
    for row in recent:
        execution = _latest_managed_execution(
            db,
            recommendation_id=row.recommendation_id,
        )
        if execution is None:
            continue
        if row.result_classification != "worse":
            break
        regressions.append((row, execution))
        if len(regressions) >= REGRESSION_PAUSE_THRESHOLD:
            break

    result = {
        **base,
        "status": "watching",
        "consecutive_regressions": len(regressions),
        "measurement_ids": [row.id for row, _execution in regressions],
        "metric_ids": [
            str((row.measurement_contract or {}).get("primary_metric_id") or "")
            for row, _execution in regressions
        ],
    }
    if len(regressions) < REGRESSION_PAUSE_THRESHOLD:
        return result

    latest_execution = regressions[0][1]
    paused_policy = pause_wordpress_automation_policy(
        db,
        campaign_id=measurement.campaign_id,
        reason_code="wordpress_repeated_measured_regression",
        execution_id=latest_execution.id,
    )
    if paused_policy is None:
        return {**result, "status": "policy_off"}
    write_audit_log(
        db,
        tenant_id=measurement.tenant_id,
        actor_user_id="InsightOS safety monitor",
        event_type="wordpress.automation_policy.regression_paused",
        payload={
            "campaign_id": measurement.campaign_id,
            "organization_id": measurement.organization_id,
            "policy_id": paused_policy.id,
            "policy_version": paused_policy.version,
            "reason_code": "wordpress_repeated_measured_regression",
            "execution_id": latest_execution.id,
            "measurement_ids": result["measurement_ids"],
            "metric_ids": result["metric_ids"],
            "causal_claim": False,
        },
    )
    db.flush()
    return {
        **result,
        "status": "paused",
        "pause_reason_code": "wordpress_repeated_measured_regression",
        "paused_execution_id": latest_execution.id,
        "automation_policy_version": int(paused_policy.version),
        "recovery_action": (
            "Review the two measured declines and the affected pages. Roll back an applicable "
            "change if needed, then remove the pause only after the website is stable."
        ),
    }


def _latest_managed_execution(
    db: Session,
    *,
    recommendation_id: str,
) -> RecommendationExecution | None:
    rows = (
        db.query(RecommendationExecution)
        .filter(
            RecommendationExecution.recommendation_id == recommendation_id,
            RecommendationExecution.status == "completed",
        )
        .order_by(
            RecommendationExecution.executed_at.desc(),
            RecommendationExecution.created_at.desc(),
        )
        .all()
    )
    return next((row for row in rows if is_managed_wordpress_execution(row)), None)

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.intelligence.lexicon import get_active_lexicon
from app.models.action_plan import (
    ActionPlanForecast,
    ActionPlanMeasurement,
    ActionPlanOccurrence,
)


MODEL_ID = "action-plan-direct-metric"
MODEL_VERSION = "1.0.0"

# Fractions represent the bounded share of the gap between the saved baseline
# and the active good threshold. They are governed assumptions, not learned
# customer coefficients and never imply ranking, traffic, lead, or revenue lift.
_MODEL_PARAMETERS: dict[str, dict[str, dict[str, float]]] = {
    "technical.reduce_render_blocking": {
        "cwv.lcp": {"conservative": 0.15, "expected": 0.30, "optimistic": 0.50},
    },
    "technical.optimize_lcp_resource": {
        "cwv.lcp": {"conservative": 0.20, "expected": 0.40, "optimistic": 0.65},
    },
    "technical.optimize_server_response": {
        "web_vital.ttfb": {
            "conservative": 0.20,
            "expected": 0.40,
            "optimistic": 0.60,
        },
        "cwv.lcp": {"conservative": 0.05, "expected": 0.12, "optimistic": 0.20},
    },
    "technical.reduce_main_thread_work": {
        "cwv.inp": {"conservative": 0.15, "expected": 0.30, "optimistic": 0.50},
    },
    "technical.optimize_interaction_handlers": {
        "cwv.inp": {"conservative": 0.20, "expected": 0.40, "optimistic": 0.60},
    },
    "technical.reserve_layout_space": {
        "cwv.cls": {"conservative": 0.30, "expected": 0.55, "optimistic": 0.80},
    },
    "technical.stabilize_dynamic_content": {
        "cwv.cls": {"conservative": 0.20, "expected": 0.45, "optimistic": 0.70},
    },
}

_ASSUMPTIONS = [
    "The checklist is completed across the saved page and device scope.",
    "No unrelated major website change materially affects the same measurement.",
    "A new field measurement is collected after the observation window.",
    "Only the directly affected speed or stability measurement is forecast.",
    "Rankings, visits, leads, and revenue remain unknown.",
]


def _hash(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def _round_metric(value: float, unit: str) -> float:
    if unit == "score":
        return round(value, 4)
    if unit in {"milliseconds", "count", "position"}:
        return round(value, 1)
    return round(value, 4)


def _scenario_value(
    *,
    baseline: float,
    target: float,
    fraction: float,
    direction: str,
) -> float:
    gap = abs(baseline - target)
    if direction == "lower_is_better":
        return baseline - (gap * fraction)
    return baseline + (gap * fraction)


def _unavailable_reason(code: str, message: str, metric_id: str | None = None) -> dict:
    return {"code": code, "metric_id": metric_id, "message": message}


def ensure_action_plan_forecast(
    db: Session,
    *,
    occurrence: ActionPlanOccurrence,
    measurement: ActionPlanMeasurement,
    generated_at: datetime | None = None,
) -> ActionPlanForecast:
    existing = (
        db.query(ActionPlanForecast)
        .filter(ActionPlanForecast.occurrence_id == occurrence.id)
        .first()
    )
    if existing is not None:
        return existing

    resolved_at = generated_at or datetime.now(UTC)
    lexicon = get_active_lexicon(db, tenant_id=occurrence.tenant_id)
    action = lexicon.action_index.get(occurrence.action_id)
    baseline_by_id = {
        str(item.get("metric_id")): item for item in measurement.baseline_metrics or []
    }
    action_parameters = _MODEL_PARAMETERS.get(occurrence.action_id, {})
    unavailable_reasons: list[dict] = []
    metric_forecasts: list[dict] = []

    scope = dict(measurement.implementation_scope or {})
    scope_is_defined = bool(
        scope.get("campaign_id")
        and scope.get("domain")
        and scope.get("action_id")
        and scope.get("affected_urls")
    )
    if not scope_is_defined:
        unavailable_reasons.append(
            _unavailable_reason(
                "scope_not_defined",
                "The affected page and website scope is not defined well enough yet.",
            )
        )
    if measurement.observation_window_days <= 0:
        unavailable_reasons.append(
            _unavailable_reason(
                "observation_window_missing",
                "The action does not have a valid waiting period for a follow-up measurement.",
            )
        )
    if action is None:
        unavailable_reasons.append(
            _unavailable_reason(
                "action_not_in_active_lexicon",
                "This saved action is not available in the active measurement standard.",
            )
        )
    elif not action_parameters:
        unavailable_reasons.append(
            _unavailable_reason(
                "model_not_supported",
                "A trustworthy numeric forecast is not available for this kind of work yet.",
            )
        )

    if action is not None and action_parameters and scope_is_defined:
        for metric_id in action.success_metric_ids:
            baseline = baseline_by_id.get(metric_id, {})
            metric = lexicon.metric_index.get(metric_id)
            parameters = action_parameters.get(metric_id)
            if parameters is None:
                unavailable_reasons.append(
                    _unavailable_reason(
                        "metric_model_not_supported",
                        "This measurement does not have an approved forecast model yet.",
                        metric_id,
                    )
                )
                continue
            if baseline.get("status") != "available" or baseline.get("value") is None:
                unavailable_reasons.append(
                    _unavailable_reason(
                        "baseline_not_available",
                        "A real starting measurement is required before a forecast can be shown.",
                        metric_id,
                    )
                )
                continue
            if metric is None or metric.thresholds is None:
                unavailable_reasons.append(
                    _unavailable_reason(
                        "target_not_available",
                        "The active standard does not define a target for this measurement.",
                        metric_id,
                    )
                )
                continue

            direction = str(metric.thresholds.direction)
            target = float(metric.thresholds.good_boundary)
            current = float(baseline["value"])
            already_at_target = (
                direction == "lower_is_better" and current <= target
            ) or (
                direction == "higher_is_better" and current >= target
            )
            if already_at_target:
                unavailable_reasons.append(
                    _unavailable_reason(
                        "already_at_target",
                        "The saved measurement already meets the active target.",
                        metric_id,
                    )
                )
                continue

            scenarios = {
                name: _round_metric(
                    _scenario_value(
                        baseline=current,
                        target=target,
                        fraction=float(fraction),
                        direction=direction,
                    ),
                    metric.unit,
                )
                for name, fraction in parameters.items()
            }
            range_values = [scenarios["conservative"], scenarios["optimistic"]]
            metric_forecasts.append(
                {
                    "metric_id": metric_id,
                    "display_name": metric.display_name,
                    "plain_language": metric.plain_language,
                    "unit": metric.unit,
                    "aggregation": metric.aggregation,
                    "direction": direction,
                    "current_value": _round_metric(current, metric.unit),
                    "target_value": _round_metric(target, metric.unit),
                    "conservative_value": scenarios["conservative"],
                    "expected_value": scenarios["expected"],
                    "optimistic_value": scenarios["optimistic"],
                    "range_low": min(range_values),
                    "range_high": max(range_values),
                    "source": baseline.get("source"),
                    "source_record_id": baseline.get("source_record_id"),
                    "measured_at": baseline.get("measured_at"),
                    "scope": baseline.get("scope"),
                    "confidence": "moderate",
                }
            )

    total_metrics = len(action.success_metric_ids) if action is not None else 0
    coverage_ratio = (
        float(len(metric_forecasts)) / float(total_metrics) if total_metrics else 0.0
    )
    forecast_status = "available" if metric_forecasts else "not_available"
    if forecast_status == "not_available":
        data_quality = "insufficient"
    elif coverage_ratio == 1.0 and all(
        item.get("source") == "Chrome UX Report field data" for item in metric_forecasts
    ):
        data_quality = "strong"
    else:
        data_quality = "moderate"

    parameters_payload = {
        "gap_closure_fractions": action_parameters,
        "target_source": "active_lexicon_good_boundary",
        "bounded_to_target": True,
    }
    input_payload = {
        "action_id": occurrence.action_id,
        "action_plan_hash": measurement.action_plan_hash,
        "baseline_metrics": measurement.baseline_metrics,
        "implementation_scope": measurement.implementation_scope,
        "observation_window_days": measurement.observation_window_days,
        "lexicon_id": measurement.lexicon_id,
        "lexicon_version": measurement.lexicon_version,
        "model_id": MODEL_ID,
        "model_version": MODEL_VERSION,
        "model_parameters": parameters_payload,
    }
    input_hash = _hash(input_payload)
    artifact_payload = {
        "input_hash": input_hash,
        "forecast_status": forecast_status,
        "metric_forecasts": metric_forecasts,
        "assumptions": _ASSUMPTIONS,
        "unavailable_reasons": unavailable_reasons,
        "data_quality": data_quality,
        "coverage_ratio": coverage_ratio,
    }
    row = ActionPlanForecast(
        tenant_id=occurrence.tenant_id,
        organization_id=occurrence.organization_id,
        campaign_id=occurrence.campaign_id,
        business_location_id=occurrence.business_location_id,
        occurrence_id=occurrence.id,
        measurement_id=measurement.id,
        recommendation_id=occurrence.recommendation_id,
        action_id=occurrence.action_id,
        forecast_status=forecast_status,
        metric_forecasts=metric_forecasts,
        assumptions=list(_ASSUMPTIONS),
        unavailable_reasons=unavailable_reasons,
        data_quality=data_quality,
        model_id=MODEL_ID,
        model_version=MODEL_VERSION,
        model_parameters={**parameters_payload, "coverage_ratio": coverage_ratio},
        input_hash=input_hash,
        artifact_hash=_hash(artifact_payload),
        action_plan_hash=measurement.action_plan_hash,
        lexicon_id=measurement.lexicon_id,
        lexicon_version=measurement.lexicon_version,
        observation_window_days=measurement.observation_window_days,
        outcome_comparisons=[],
        compared_at=None,
        generated_at=resolved_at,
        created_at=resolved_at,
        updated_at=resolved_at,
    )
    db.add(row)
    db.flush()
    return row


def generate_action_plan_forecast(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
    occurrence_id: str,
    generated_at: datetime | None = None,
) -> ActionPlanForecast:
    occurrence = (
        db.query(ActionPlanOccurrence)
        .filter(
            ActionPlanOccurrence.id == occurrence_id,
            ActionPlanOccurrence.tenant_id == tenant_id,
            ActionPlanOccurrence.organization_id == organization_id,
            ActionPlanOccurrence.campaign_id == campaign_id,
        )
        .with_for_update()
        .first()
    )
    if occurrence is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action plan not found")
    measurement = (
        db.query(ActionPlanMeasurement)
        .filter(
            ActionPlanMeasurement.tenant_id == tenant_id,
            ActionPlanMeasurement.organization_id == organization_id,
            ActionPlanMeasurement.occurrence_id == occurrence_id,
        )
        .first()
    )
    if measurement is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Start the checklist before creating a forecast.",
        )
    row = ensure_action_plan_forecast(
        db,
        occurrence=occurrence,
        measurement=measurement,
        generated_at=generated_at,
    )
    db.commit()
    db.refresh(row)
    return row


def compare_forecast_to_outcome(
    db: Session,
    *,
    forecast: ActionPlanForecast,
    measurement: ActionPlanMeasurement,
    compared_at: datetime,
) -> ActionPlanForecast:
    if forecast.compared_at is not None:
        return forecast
    observed_by_id = {
        str(item.get("metric_id")): item for item in measurement.outcome_metrics or []
    }
    comparisons: list[dict] = []
    for item in forecast.metric_forecasts or []:
        metric_id = str(item.get("metric_id"))
        observed = observed_by_id.get(metric_id, {})
        observed_value = observed.get("value")
        if (
            observed.get("comparison") == "insufficient_data"
            or observed_value is None
            or item.get("range_low") is None
            or item.get("range_high") is None
        ):
            comparisons.append(
                {
                    "metric_id": metric_id,
                    "status": "insufficient_data",
                    "position": "unknown",
                    "observed_value": observed_value,
                }
            )
            continue

        value = float(observed_value)
        low = float(item["range_low"])
        high = float(item["range_high"])
        if low <= value <= high:
            comparison_status = "within_range"
            position = "within_range"
        else:
            comparison_status = "outside_range"
            if item.get("direction") == "lower_is_better":
                position = "better_than_range" if value < low else "worse_than_range"
            else:
                position = "better_than_range" if value > high else "worse_than_range"
        comparisons.append(
            {
                "metric_id": metric_id,
                "status": comparison_status,
                "position": position,
                "observed_value": value,
                "range_low": low,
                "range_high": high,
                "expected_value": item.get("expected_value"),
            }
        )

    forecast.outcome_comparisons = comparisons
    forecast.compared_at = compared_at
    forecast.updated_at = compared_at
    db.flush()
    return forecast


def get_action_plan_forecast(
    db: Session,
    *,
    occurrence_id: str,
) -> ActionPlanForecast | None:
    return (
        db.query(ActionPlanForecast)
        .filter(ActionPlanForecast.occurrence_id == occurrence_id)
        .first()
    )


def serialize_action_plan_forecast(forecast: ActionPlanForecast) -> dict[str, Any]:
    return {
        "id": forecast.id,
        "forecast_status": forecast.forecast_status,
        "metric_forecasts": list(forecast.metric_forecasts or []),
        "assumptions": list(forecast.assumptions or []),
        "unavailable_reasons": list(forecast.unavailable_reasons or []),
        "data_quality": forecast.data_quality,
        "model_id": forecast.model_id,
        "model_version": forecast.model_version,
        "input_hash": forecast.input_hash,
        "artifact_hash": forecast.artifact_hash,
        "action_plan_hash": forecast.action_plan_hash,
        "lexicon_id": forecast.lexicon_id,
        "lexicon_version": forecast.lexicon_version,
        "observation_window_days": forecast.observation_window_days,
        "outcome_comparisons": list(forecast.outcome_comparisons or []),
        "compared_at": forecast.compared_at.isoformat() if forecast.compared_at else None,
        "generated_at": forecast.generated_at.isoformat(),
        "promise": False,
        "unknown_effects": ["rankings", "visits", "leads", "revenue"],
    }

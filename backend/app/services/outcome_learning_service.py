from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.action_plan import ActionPlanForecast, ActionPlanMeasurement
from app.models.campaign import Campaign
from app.models.intelligence import StrategyRecommendation


MINIMUM_COMPARABLE_OUTCOMES = 5


def get_campaign_outcome_learning(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
    limit: int = 100,
) -> dict[str, Any]:
    """Build a review-only learning view from governed action measurements.

    The result deliberately does not mutate recommendation rules, forecast models,
    or experiment assignments. It only groups comparable measured outcomes so a
    later reviewed policy change can cite the exact evidence it used.
    """

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

    rows = (
        db.query(ActionPlanMeasurement, ActionPlanForecast, StrategyRecommendation)
        .join(
            StrategyRecommendation,
            StrategyRecommendation.id == ActionPlanMeasurement.recommendation_id,
        )
        .outerjoin(
            ActionPlanForecast,
            ActionPlanForecast.occurrence_id == ActionPlanMeasurement.occurrence_id,
        )
        .filter(
            ActionPlanMeasurement.tenant_id == tenant_id,
            ActionPlanMeasurement.organization_id == organization_id,
            ActionPlanMeasurement.campaign_id == campaign_id,
            ActionPlanMeasurement.measurement_status == "measured",
            StrategyRecommendation.tenant_id == tenant_id,
            StrategyRecommendation.campaign_id == campaign_id,
        )
        .order_by(
            ActionPlanMeasurement.outcome_measured_at.desc(),
            ActionPlanMeasurement.id.desc(),
        )
        .limit(limit)
        .all()
    )

    observations = [
        _serialize_observation(measurement, forecast, recommendation)
        for measurement, forecast, recommendation in rows
    ]
    comparable = [item for item in observations if item["comparable"]]
    group_members: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for item in comparable:
        group_members[
            (
                item["action_id"],
                item["metric_id"] or "unknown",
                item["measurement_contract_version"],
            )
        ].append(item)

    groups = [
        _summarize_group(action_id, metric_id, contract_version, items)
        for (action_id, metric_id, contract_version), items in sorted(
            group_members.items(),
            key=lambda pair: (-len(pair[1]), pair[0]),
        )
    ]
    forecast_checks = [
        item
        for item in comparable
        if item["forecast_check"]["status"] in {"within_range", "outside_range"}
    ]
    within_range = sum(
        1 for item in forecast_checks if item["forecast_check"]["position"] == "within_range"
    )
    better_than_range = sum(
        1
        for item in forecast_checks
        if item["forecast_check"]["position"] == "better_than_range"
    )
    worse_than_range = sum(
        1
        for item in forecast_checks
        if item["forecast_check"]["position"] == "worse_than_range"
    )

    improved_count = sum(
        1 for item in observations if item["result_classification"] == "improved"
    )
    unchanged_count = sum(
        1
        for item in observations
        if item["result_classification"] == "about_the_same"
    )
    worse_count = sum(
        1 for item in observations if item["result_classification"] == "worse"
    )
    insufficient_count = len(observations) - len(comparable)
    review_ready_groups = sum(1 for group in groups if group["review_ready"])
    latest_measured_at = observations[0]["measured_at"] if observations else None

    return {
        "campaign_id": campaign_id,
        "summary": {
            "measured_actions": len(observations),
            "comparable_outcomes": len(comparable),
            "improved_count": improved_count,
            "unchanged_count": unchanged_count,
            "worse_count": worse_count,
            "insufficient_count": insufficient_count,
            "forecast_checks": len(forecast_checks),
            "within_range_count": within_range,
            "better_than_range_count": better_than_range,
            "worse_than_range_count": worse_than_range,
            "review_ready_groups": review_ready_groups,
            "latest_measured_at": latest_measured_at,
        },
        "learning": {
            "state": "review_only",
            "minimum_comparable_outcomes": MINIMUM_COMPARABLE_OUTCOMES,
            "automatic_policy_updates_enabled": False,
            "automatic_experiments_enabled": False,
            "causal_claims_allowed": False,
            "forecast_review_ready": len(forecast_checks) >= MINIMUM_COMPARABLE_OUTCOMES,
            "message": (
                "Enough comparable results exist for a person to review the evidence. "
                "InsightOS has not changed any rules or forecasts."
                if review_ready_groups
                else "InsightOS is saving comparable results. It will not change its rules or forecasts from a small sample."
            ),
        },
        "groups": groups,
        "observations": observations,
    }


def _serialize_observation(
    measurement: ActionPlanMeasurement,
    forecast: ActionPlanForecast | None,
    recommendation: StrategyRecommendation,
) -> dict[str, Any]:
    contract = dict(measurement.measurement_contract or {})
    metric_id = str(
        contract.get("primary_metric_id")
        or next(iter(measurement.success_metric_ids or []), "")
    ).strip()
    baseline = _metric_by_id(measurement.baseline_metrics, metric_id)
    outcome = _metric_by_id(measurement.outcome_metrics, metric_id)
    forecast_comparison = _metric_by_id(
        forecast.outcome_comparisons if forecast is not None else [],
        metric_id,
    )
    source_matches = bool(
        baseline.get("source")
        and outcome.get("source")
        and baseline.get("source") == outcome.get("source")
    )
    scope_matches = outcome.get("scope_matches") is not False
    result_classification = str(measurement.result_classification or "")
    comparable = bool(
        result_classification in {"improved", "about_the_same", "worse"}
        and baseline.get("status") == "available"
        and outcome.get("status") == "available"
        and baseline.get("value") is not None
        and outcome.get("value") is not None
        and outcome.get("comparison_requirements_met") is True
        and scope_matches
    )
    evidence_quality = (
        "strong"
        if comparable and source_matches
        else "moderate"
        if comparable
        else "insufficient"
    )
    confounders = _confounders(contract)
    return {
        "measurement_id": measurement.id,
        "occurrence_id": measurement.occurrence_id,
        "recommendation_id": measurement.recommendation_id,
        "action_id": measurement.action_id,
        "action_label": _humanize_action_id(measurement.action_id),
        "recommendation_reason": recommendation.rationale,
        "measurement_track": str(contract.get("track") or "website"),
        "measurement_contract_version": str(contract.get("version") or "unknown"),
        "metric_id": metric_id or None,
        "metric_label": str(
            outcome.get("display_name")
            or baseline.get("display_name")
            or _humanize_metric_id(metric_id)
        ),
        "direction": outcome.get("direction") or baseline.get("direction"),
        "baseline": _metric_summary(baseline),
        "outcome": _metric_summary(outcome),
        "result_classification": result_classification,
        "outcome_status": measurement.outcome_status,
        "evidence_quality": evidence_quality,
        "comparable": comparable,
        "confounders": confounders,
        "forecast_check": {
            "forecast_id": forecast.id if forecast is not None else None,
            "model_id": forecast.model_id if forecast is not None else None,
            "model_version": forecast.model_version if forecast is not None else None,
            "status": str(forecast_comparison.get("status") or "not_checked"),
            "position": str(forecast_comparison.get("position") or "unknown"),
            "range_low": forecast_comparison.get("range_low"),
            "range_high": forecast_comparison.get("range_high"),
            "observed_value": forecast_comparison.get("observed_value"),
        },
        "baseline_captured_at": _iso(measurement.baseline_captured_at),
        "work_completed_at": _iso(measurement.work_completed_at),
        "measured_at": _iso(measurement.outcome_measured_at),
        "observation_window_days": measurement.observation_window_days,
        "lexicon_id": measurement.lexicon_id,
        "lexicon_version": measurement.lexicon_version,
        "causal_proof": False,
    }


def _summarize_group(
    action_id: str,
    metric_id: str,
    contract_version: str,
    items: list[dict[str, Any]],
) -> dict[str, Any]:
    forecast_items = [
        item
        for item in items
        if item["forecast_check"]["status"] in {"within_range", "outside_range"}
    ]
    samples = len(items)
    review_ready = samples >= MINIMUM_COMPARABLE_OUTCOMES
    return {
        "action_id": action_id,
        "action_label": items[0]["action_label"],
        "measurement_track": items[0]["measurement_track"],
        "metric_id": None if metric_id == "unknown" else metric_id,
        "metric_label": items[0]["metric_label"],
        "measurement_contract_version": contract_version,
        "sample_count": samples,
        "improved_count": sum(
            1 for item in items if item["result_classification"] == "improved"
        ),
        "unchanged_count": sum(
            1
            for item in items
            if item["result_classification"] == "about_the_same"
        ),
        "worse_count": sum(
            1 for item in items if item["result_classification"] == "worse"
        ),
        "forecast_check_count": len(forecast_items),
        "forecast_within_range_count": sum(
            1
            for item in forecast_items
            if item["forecast_check"]["position"] == "within_range"
        ),
        "review_ready": review_ready,
        "review_state": "ready_for_human_review" if review_ready else "needs_more_examples",
        "examples_needed": max(0, MINIMUM_COMPARABLE_OUTCOMES - samples),
        "automatic_changes_allowed": False,
    }


def _metric_by_id(items: list | None, metric_id: str) -> dict[str, Any]:
    for raw in items or []:
        if isinstance(raw, dict) and str(raw.get("metric_id") or "") == metric_id:
            return dict(raw)
    return {}


def _metric_summary(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": item.get("status") or "unavailable",
        "value": item.get("value"),
        "unit": item.get("unit"),
        "source": item.get("source"),
        "source_record_id": item.get("source_record_id"),
        "measured_at": item.get("measured_at") or item.get("captured_at"),
    }


def _confounders(contract: dict[str, Any]) -> list[dict[str, str]]:
    result = contract.get("result") if isinstance(contract.get("result"), dict) else {}
    raw = result.get("confounders") if isinstance(result, dict) else []
    return [
        {
            "code": str(item.get("code") or "other_change"),
            "label": str(item.get("label") or "Another change may have affected this result"),
        }
        for item in raw or []
        if isinstance(item, dict)
    ]


def _humanize_action_id(value: str) -> str:
    words = str(value or "action").split(".")[-1].replace("_", " ").strip()
    return words[:1].upper() + words[1:] if words else "Completed action"


def _humanize_metric_id(value: str) -> str:
    words = str(value or "measurement").split(".")[-1].replace("_", " ").strip()
    return words.upper() if words in {"lcp", "inp", "cls"} else words[:1].upper() + words[1:]


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None

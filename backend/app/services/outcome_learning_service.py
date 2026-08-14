from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.action_plan import ActionPlanForecast, ActionPlanMeasurement
from app.models.campaign import Campaign
from app.models.intelligence import StrategyRecommendation
from app.models.outcome_learning import OutcomeLearningReview
from app.services.audit_service import write_audit_log


MINIMUM_COMPARABLE_OUTCOMES = 5
CONFOUNDER_LABELS = {
    "other_website_changes": "Other website changes happened",
    "google_or_search_change": "Google or search results changed",
    "seasonal_demand": "Customer demand changed with the season",
    "tracking_change": "Tracking or measurement changed",
    "other_marketing": "Other marketing was running",
    "website_outage": "The website had an outage or major problem",
    "other": "Something else may have affected the result",
}


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
        db.query(
            ActionPlanMeasurement,
            ActionPlanForecast,
            StrategyRecommendation,
            OutcomeLearningReview,
        )
        .join(
            StrategyRecommendation,
            StrategyRecommendation.id == ActionPlanMeasurement.recommendation_id,
        )
        .outerjoin(
            ActionPlanForecast,
            ActionPlanForecast.occurrence_id == ActionPlanMeasurement.occurrence_id,
        )
        .outerjoin(
            OutcomeLearningReview,
            OutcomeLearningReview.measurement_id == ActionPlanMeasurement.id,
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
        _serialize_observation(measurement, forecast, recommendation, review)
        for measurement, forecast, recommendation, review in rows
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
    learning_eligible = [
        item for item in comparable if item["review"]["learning_eligible"]
    ]
    forecast_checks = [
        item
        for item in learning_eligible
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
    pending_review_count = sum(
        1 for item in observations if item["review"]["decision"] == "pending"
    )
    included_count = sum(
        1 for item in observations if item["review"]["decision"] == "included"
    )
    excluded_count = sum(
        1 for item in observations if item["review"]["decision"] == "excluded"
    )
    review_ready_groups = sum(1 for group in groups if group["review_ready"])
    latest_measured_at = observations[0]["measured_at"] if observations else None

    return {
        "campaign_id": campaign_id,
        "summary": {
            "measured_actions": len(observations),
            "comparable_outcomes": len(comparable),
            "learning_eligible_outcomes": len(learning_eligible),
            "pending_review_count": pending_review_count,
            "included_count": included_count,
            "excluded_count": excluded_count,
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
                "Enough owner-reviewed results exist for a person to review this evidence group. "
                "InsightOS still has not changed any rules or forecasts."
                if review_ready_groups
                else (
                    f"Review {pending_review_count} measured result"
                    f"{'s' if pending_review_count != 1 else ''} before they can inform learning. "
                    "InsightOS will not change its rules or forecasts on its own."
                    if pending_review_count
                    else "InsightOS is saving owner-reviewed results. It will not change its rules or forecasts from a small sample."
                )
            ),
        },
        "groups": groups,
        "observations": observations,
    }


def _serialize_observation(
    measurement: ActionPlanMeasurement,
    forecast: ActionPlanForecast | None,
    recommendation: StrategyRecommendation,
    review: OutcomeLearningReview | None = None,
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
    result_classification = str(measurement.result_classification or "")
    comparable = _measurement_comparable(
        measurement,
        metric_id=metric_id,
        baseline=baseline,
        outcome=outcome,
    )
    evidence_quality = (
        "strong"
        if comparable and source_matches
        else "moderate"
        if comparable
        else "insufficient"
    )
    confounders = _confounders(contract)
    review_payload = _serialize_review(review, comparable=comparable)
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
        "review": review_payload,
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
    included_items = [
        item
        for item in items
        if item.get("review", {}).get("decision") == "included"
        and item.get("comparable", True)
    ]
    forecast_items = [
        item
        for item in included_items
        if item["forecast_check"]["status"] in {"within_range", "outside_range"}
    ]
    samples = len(items)
    included_count = len(included_items)
    pending_review_count = sum(
        1 for item in items if item.get("review", {}).get("decision") == "pending"
    )
    excluded_count = sum(
        1 for item in items if item.get("review", {}).get("decision") == "excluded"
    )
    review_ready = included_count >= MINIMUM_COMPARABLE_OUTCOMES
    return {
        "action_id": action_id,
        "action_label": items[0]["action_label"],
        "measurement_track": items[0]["measurement_track"],
        "metric_id": None if metric_id == "unknown" else metric_id,
        "metric_label": items[0]["metric_label"],
        "measurement_contract_version": contract_version,
        "sample_count": samples,
        "included_count": included_count,
        "pending_review_count": pending_review_count,
        "excluded_count": excluded_count,
        "improved_count": sum(
            1
            for item in included_items
            if item["result_classification"] == "improved"
        ),
        "unchanged_count": sum(
            1
            for item in included_items
            if item["result_classification"] == "about_the_same"
        ),
        "worse_count": sum(
            1 for item in included_items if item["result_classification"] == "worse"
        ),
        "forecast_check_count": len(forecast_items),
        "forecast_within_range_count": sum(
            1
            for item in forecast_items
            if item["forecast_check"]["position"] == "within_range"
        ),
        "review_ready": review_ready,
        "review_state": (
            "ready_for_human_review"
            if review_ready
            else "needs_human_review"
            if pending_review_count
            else "needs_more_included_examples"
        ),
        "examples_needed": max(0, MINIMUM_COMPARABLE_OUTCOMES - included_count),
        "automatic_changes_allowed": False,
    }


def review_outcome_learning(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
    measurement_id: str,
    actor_user_id: str,
    decision: str,
    confounder_codes: list[str] | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    """Save a tenant-scoped human judgment without changing any learned policy."""

    codes = list(dict.fromkeys(confounder_codes or []))
    normalized_note = str(note or "").strip() or None
    if decision not in {"pending", "included", "excluded"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Choose whether to use this result, leave it out, or clear the review",
        )
    if any(code not in CONFOUNDER_LABELS for code in codes):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="One or more result context choices are not supported",
        )
    if decision == "pending":
        codes = []
        normalized_note = None
    if "other" in codes and not normalized_note:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Add a short note explaining what else may have affected the result",
        )

    measurement = (
        db.query(ActionPlanMeasurement)
        .filter(
            ActionPlanMeasurement.id == measurement_id,
            ActionPlanMeasurement.tenant_id == tenant_id,
            ActionPlanMeasurement.organization_id == organization_id,
            ActionPlanMeasurement.campaign_id == campaign_id,
        )
        .first()
    )
    if measurement is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Measured result not found",
        )
    if measurement.measurement_status != "measured":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This work does not have a follow-up result yet",
        )
    comparable = _measurement_comparable(measurement)
    if decision == "included" and not comparable:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This result does not have enough matching information to use for learning",
        )

    row = (
        db.query(OutcomeLearningReview)
        .filter(
            OutcomeLearningReview.measurement_id == measurement_id,
            OutcomeLearningReview.tenant_id == tenant_id,
            OutcomeLearningReview.organization_id == organization_id,
        )
        .first()
    )
    if row is None:
        row = OutcomeLearningReview(
            tenant_id=tenant_id,
            organization_id=organization_id,
            campaign_id=campaign_id,
            business_location_id=measurement.business_location_id,
            measurement_id=measurement_id,
        )
        db.add(row)

    current_codes = list(row.confounder_codes or [])
    unchanged = (
        row.decision == decision
        and current_codes == codes
        and row.note == normalized_note
    )
    if not unchanged:
        now = datetime.now(UTC)
        row.decision = decision
        row.confounder_codes = codes
        row.note = normalized_note
        row.reviewed_by_user_id = actor_user_id if decision != "pending" else None
        row.reviewed_at = now if decision != "pending" else None
        row.updated_at = now
        write_audit_log(
            db,
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            event_type="intelligence.outcome_learning_reviewed",
            payload={
                "campaign_id": campaign_id,
                "measurement_id": measurement_id,
                "decision": decision,
                "confounder_codes": codes,
                "note_provided": normalized_note is not None,
                "automatic_policy_updates_enabled": False,
                "automatic_experiments_enabled": False,
            },
        )
        db.commit()
        db.refresh(row)

    return _serialize_review(
        row,
        comparable=comparable,
    )


def _serialize_review(
    review: OutcomeLearningReview | None,
    *,
    comparable: bool,
) -> dict[str, Any]:
    decision = review.decision if review is not None else "pending"
    codes = list(review.confounder_codes or []) if review is not None else []
    return {
        "decision": decision,
        "confounder_codes": codes,
        "confounders": [
            {"code": code, "label": CONFOUNDER_LABELS.get(code, code)}
            for code in codes
        ],
        "note": review.note if review is not None else None,
        "reviewed_at": _iso(review.reviewed_at) if review is not None else None,
        "reviewed_by_user_id": (
            review.reviewed_by_user_id if review is not None else None
        ),
        "learning_eligible": bool(comparable and decision == "included"),
    }


def _measurement_comparable(
    measurement: ActionPlanMeasurement,
    *,
    metric_id: str | None = None,
    baseline: dict[str, Any] | None = None,
    outcome: dict[str, Any] | None = None,
) -> bool:
    contract = dict(measurement.measurement_contract or {})
    resolved_metric_id = str(
        metric_id
        or contract.get("primary_metric_id")
        or next(iter(measurement.success_metric_ids or []), "")
    ).strip()
    baseline_metric = baseline or _metric_by_id(
        measurement.baseline_metrics,
        resolved_metric_id,
    )
    outcome_metric = outcome or _metric_by_id(
        measurement.outcome_metrics,
        resolved_metric_id,
    )
    return bool(
        measurement.result_classification
        in {"improved", "about_the_same", "worse"}
        and baseline_metric.get("status") == "available"
        and outcome_metric.get("status") == "available"
        and baseline_metric.get("value") is not None
        and outcome_metric.get("value") is not None
        and outcome_metric.get("comparison_requirements_met") is True
        and outcome_metric.get("scope_matches") is not False
    )


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

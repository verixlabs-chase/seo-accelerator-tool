from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.action_plan import ActionPlanMeasurement
from app.models.campaign import Campaign
from app.models.governed_experiment import (
    GovernedExperimentPlan,
    GovernedExperimentProtocol,
    GovernedPolicyCandidate,
    GovernedPolicyDecision,
    GovernedPolicyReplay,
)
from app.models.outcome_learning import OutcomeLearningReview
from app.services.audit_service import write_audit_log


POLICY_FAMILY = "action_learning_eligibility"
CANDIDATE_VERSION = "1.0"
REPLAY_VERSION = "1.0"
CHAMPION_MINIMUM_OUTCOMES = 5
CHALLENGER_MINIMUM_IMPROVEMENT_RATIO = 0.60
CHALLENGER_MAXIMUM_WORSE_RATIO = 0.25
CHALLENGER_MINIMUM_IMPROVEMENT_WILSON_LOWER = 0.35
WILSON_Z_90 = 1.6448536269514722
APPROVAL_ACKNOWLEDGEMENTS = (
    "reviewed_rule_comparison",
    "understands_not_active",
    "understands_no_causal_proof",
)


def list_candidates(
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
        db.query(GovernedPolicyCandidate)
        .filter(
            GovernedPolicyCandidate.tenant_id == tenant_id,
            GovernedPolicyCandidate.organization_id == organization_id,
            GovernedPolicyCandidate.campaign_id == campaign_id,
            GovernedPolicyCandidate.policy_family == POLICY_FAMILY,
        )
        .order_by(
            GovernedPolicyCandidate.created_at.desc(),
            GovernedPolicyCandidate.id.desc(),
        )
        .all()
    )
    return {
        "items": [_serialize_item(db, row) for row in rows],
        "count": len(rows),
        "safety": _safety(),
    }


def create_candidate(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
    protocol_id: str,
    actor_user_id: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    protocol = _protocol_or_404(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=campaign_id,
        protocol_id=protocol_id,
    )
    existing = (
        db.query(GovernedPolicyCandidate)
        .filter(
            GovernedPolicyCandidate.tenant_id == tenant_id,
            GovernedPolicyCandidate.protocol_id == protocol_id,
            GovernedPolicyCandidate.policy_family == POLICY_FAMILY,
        )
        .first()
    )
    if existing is not None:
        return {"created": False, "item": _serialize_item(db, existing)}
    if protocol.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Finish the controlled test before reviewing a stricter learning rule",
        )

    plan = _plan_or_404(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=campaign_id,
        plan_id=protocol.plan_id,
    )
    if plan.status != "approved" or plan.artifact_hash != protocol.plan_artifact_hash:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The completed test no longer matches its approved design",
        )

    outcomes = _matching_owner_included_outcomes(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=campaign_id,
        plan=plan,
    )
    if len(outcomes) < CHAMPION_MINIMUM_OUTCOMES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Review at least five matching measured results before creating a rule candidate"
            ),
        )

    champion_rule = {
        "policy_family": POLICY_FAMILY,
        "minimum_owner_included_matching_outcomes": CHAMPION_MINIMUM_OUTCOMES,
        "completed_protocol_required": False,
        "minimum_improvement_ratio": None,
        "maximum_worse_ratio": None,
        "minimum_improvement_wilson_lower_90": None,
    }
    challenger_rule = {
        "policy_family": POLICY_FAMILY,
        "minimum_owner_included_matching_outcomes": max(int(plan.minimum_sample_size), 10),
        "completed_protocol_required": True,
        "minimum_improvement_ratio": CHALLENGER_MINIMUM_IMPROVEMENT_RATIO,
        "maximum_worse_ratio": CHALLENGER_MAXIMUM_WORSE_RATIO,
        "minimum_improvement_wilson_lower_90": (CHALLENGER_MINIMUM_IMPROVEMENT_WILSON_LOWER),
        "wilson_confidence_level": 0.90,
    }
    evidence_snapshot = {
        "action_id": plan.action_id,
        "metric_id": plan.metric_id,
        "measurement_contract_version": plan.measurement_contract_version,
        "protocol_status": protocol.status,
        "plan_minimum_sample_size": plan.minimum_sample_size,
        "outcomes": outcomes,
        "distinct_measurement_count": len(outcomes),
    }
    evidence_hash = _hash(evidence_snapshot)
    candidate_artifact = {
        "candidate_version": CANDIDATE_VERSION,
        "policy_family": POLICY_FAMILY,
        "protocol_id": protocol.id,
        "plan_id": plan.id,
        "protocol_hash": protocol.protocol_hash,
        "champion_rule": champion_rule,
        "challenger_rule": challenger_rule,
        "evidence_hash": evidence_hash,
    }
    candidate_hash = _hash(candidate_artifact)
    created_at = _aware(now or datetime.now(UTC))
    row = GovernedPolicyCandidate(
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=campaign_id,
        business_location_id=protocol.business_location_id,
        protocol_id=protocol.id,
        plan_id=plan.id,
        policy_family=POLICY_FAMILY,
        candidate_version=CANDIDATE_VERSION,
        champion_rule=champion_rule,
        challenger_rule=challenger_rule,
        evidence_snapshot=evidence_snapshot,
        evidence_hash=evidence_hash,
        protocol_hash=protocol.protocol_hash,
        candidate_hash=candidate_hash,
        idempotency_key=_hash(
            {
                "tenant_id": tenant_id,
                "protocol_id": protocol.id,
                "policy_family": POLICY_FAMILY,
                "candidate_hash": candidate_hash,
            }
        ),
        automatic_activation_allowed=False,
        created_by_user_id=actor_user_id,
        created_at=created_at,
    )
    db.add(row)
    db.flush()
    _audit(
        db,
        row=row,
        actor_user_id=actor_user_id,
        event_type="intelligence.governed_policy_candidate_created",
        extra={"distinct_measurement_count": len(outcomes)},
    )
    db.commit()
    db.refresh(row)
    return {"created": True, "item": _serialize_item(db, row)}


def replay_candidate(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
    candidate_id: str,
    actor_user_id: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    candidate = _candidate_or_404(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=campaign_id,
        candidate_id=candidate_id,
    )
    _verify_candidate_hash(candidate)
    replay_key = _hash(
        {
            "candidate_hash": candidate.candidate_hash,
            "evidence_hash": candidate.evidence_hash,
            "replay_version": REPLAY_VERSION,
        }
    )
    existing = (
        db.query(GovernedPolicyReplay)
        .filter(
            GovernedPolicyReplay.tenant_id == tenant_id,
            GovernedPolicyReplay.idempotency_key == replay_key,
        )
        .first()
    )
    if existing is not None:
        return {"created": False, "item": _serialize_item(db, candidate)}

    outcomes = _frozen_distinct_outcomes(candidate)
    prefixes = [
        _evaluate_prefix(
            outcomes[:prefix_size],
            challenger_rule=dict(candidate.challenger_rule or {}),
            protocol_completed=(
                str((candidate.evidence_snapshot or {}).get("protocol_status")) == "completed"
            ),
        )
        for prefix_size in range(1, len(outcomes) + 1)
    ]
    final_result = prefixes[-1] if prefixes else _empty_final_result()
    replay_artifact = {
        "replay_version": REPLAY_VERSION,
        "candidate_hash": candidate.candidate_hash,
        "evidence_hash": candidate.evidence_hash,
        "ordered_measurement_ids": [item["measurement_id"] for item in outcomes],
        "cumulative_results": prefixes,
        "final_result": final_result,
    }
    replayed_at = _aware(now or datetime.now(UTC))
    replay = GovernedPolicyReplay(
        candidate_id=candidate.id,
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=campaign_id,
        replay_version=REPLAY_VERSION,
        status="passed" if final_result["eligible"] else "blocked",
        candidate_hash=candidate.candidate_hash,
        evidence_hash=candidate.evidence_hash,
        ordered_measurement_ids=replay_artifact["ordered_measurement_ids"],
        cumulative_results=prefixes,
        final_result=final_result,
        artifact_hash=_hash(replay_artifact),
        idempotency_key=replay_key,
        automatic_activation_allowed=False,
        replayed_by_user_id=actor_user_id,
        replayed_at=replayed_at,
    )
    db.add(replay)
    db.flush()
    _audit(
        db,
        row=candidate,
        actor_user_id=actor_user_id,
        event_type="intelligence.governed_policy_candidate_replayed",
        extra={
            "replay_id": replay.id,
            "replay_status": replay.status,
            "sample_count": final_result["sample_count"],
            "replay_artifact_hash": replay.artifact_hash,
        },
    )
    db.commit()
    db.refresh(replay)
    return {"created": True, "item": _serialize_item(db, candidate)}


def review_candidate(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
    candidate_id: str,
    actor_user_id: str,
    decision: str,
    replay_id: str | None,
    acknowledgements: dict[str, bool],
    note: str | None,
    now: datetime | None = None,
) -> dict[str, Any]:
    if decision not in {
        "approved_for_future_activation",
        "rejected",
        "cancelled",
    }:
        raise HTTPException(status_code=422, detail="Choose a supported final decision")
    candidate = _candidate_or_404(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=campaign_id,
        candidate_id=candidate_id,
        lock_for_update=True,
    )
    _verify_candidate_hash(candidate)
    existing = (
        db.query(GovernedPolicyDecision)
        .filter(
            GovernedPolicyDecision.tenant_id == tenant_id,
            GovernedPolicyDecision.candidate_id == candidate.id,
        )
        .first()
    )
    if existing is not None:
        if existing.decision != decision:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This rule candidate already has a different final decision",
            )
        return {"created": False, "item": _serialize_item(db, candidate)}

    replay: GovernedPolicyReplay | None = None
    saved_acknowledgements = {key: False for key in APPROVAL_ACKNOWLEDGEMENTS}
    if decision == "approved_for_future_activation":
        missing = [
            key for key in APPROVAL_ACKNOWLEDGEMENTS if acknowledgements.get(key) is not True
        ]
        if missing:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Confirm the exact passing replay, no-live-change notice, and separate future approval"
                ),
            )
        latest = _latest_replay(db, candidate)
        if replay_id:
            replay = _replay_or_404(
                db,
                tenant_id=tenant_id,
                organization_id=organization_id,
                campaign_id=campaign_id,
                candidate_id=candidate.id,
                replay_id=replay_id,
            )
        else:
            replay = latest
        if replay is None or latest is None or latest.id != replay.id or replay.status != "passed":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Approve only the latest exact replay after it passes every saved check",
            )
        _verify_replay_hash(candidate, replay)
        saved_acknowledgements = {key: True for key in APPROVAL_ACKNOWLEDGEMENTS}

    normalized_note = str(note or "").strip() or None
    decided_at = _aware(now or datetime.now(UTC))
    decision_artifact = {
        "candidate_id": candidate.id,
        "candidate_hash": candidate.candidate_hash,
        "replay_id": replay.id if replay is not None else None,
        "replay_artifact_hash": replay.artifact_hash if replay is not None else None,
        "decision": decision,
        "acknowledgements": saved_acknowledgements,
    }
    decision_hash = _hash(decision_artifact)
    row = GovernedPolicyDecision(
        candidate_id=candidate.id,
        replay_id=replay.id if replay is not None else None,
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=campaign_id,
        decision=decision,
        acknowledgements=saved_acknowledgements,
        review_note=normalized_note,
        candidate_hash=candidate.candidate_hash,
        replay_artifact_hash=replay.artifact_hash if replay is not None else None,
        decision_hash=decision_hash,
        idempotency_key=_hash(
            {
                "tenant_id": tenant_id,
                "candidate_id": candidate.id,
                "decision_hash": decision_hash,
            }
        ),
        automatic_activation_allowed=False,
        decided_by_user_id=actor_user_id,
        decided_at=decided_at,
    )
    db.add(row)
    db.flush()
    _audit(
        db,
        row=candidate,
        actor_user_id=actor_user_id,
        event_type="intelligence.governed_policy_candidate_reviewed",
        extra={
            "decision_id": row.id,
            "decision": decision,
            "replay_id": replay.id if replay is not None else None,
            "note_provided": normalized_note is not None,
            "all_approval_acknowledgements_confirmed": (
                decision == "approved_for_future_activation"
            ),
        },
    )
    db.commit()
    db.refresh(row)
    return {"created": True, "item": _serialize_item(db, candidate)}


def _matching_owner_included_outcomes(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
    plan: GovernedExperimentPlan,
) -> list[dict[str, Any]]:
    rows = (
        db.query(ActionPlanMeasurement)
        .join(
            OutcomeLearningReview,
            OutcomeLearningReview.measurement_id == ActionPlanMeasurement.id,
        )
        .filter(
            ActionPlanMeasurement.tenant_id == tenant_id,
            ActionPlanMeasurement.organization_id == organization_id,
            ActionPlanMeasurement.campaign_id == campaign_id,
            ActionPlanMeasurement.action_id == plan.action_id,
            ActionPlanMeasurement.measurement_status == "measured",
            OutcomeLearningReview.tenant_id == tenant_id,
            OutcomeLearningReview.organization_id == organization_id,
            OutcomeLearningReview.campaign_id == campaign_id,
            OutcomeLearningReview.decision == "included",
        )
        .order_by(
            ActionPlanMeasurement.outcome_measured_at.asc(),
            ActionPlanMeasurement.id.asc(),
        )
        .all()
    )
    distinct: dict[str, dict[str, Any]] = {}
    for row in rows:
        contract = dict(row.measurement_contract or {})
        primary_metric_id = str(
            contract.get("primary_metric_id") or next(iter(row.success_metric_ids or []), "")
        ).strip()
        if primary_metric_id != plan.metric_id:
            continue
        if str(contract.get("version") or "") != plan.measurement_contract_version:
            continue
        if row.result_classification not in {
            "improved",
            "about_the_same",
            "worse",
        }:
            continue
        if not _has_comparable_metric(row, primary_metric_id):
            continue
        distinct[row.id] = {
            "measurement_id": row.id,
            "result_classification": row.result_classification,
            "measured_at": _iso(row.outcome_measured_at),
        }
    return sorted(
        distinct.values(),
        key=lambda item: (str(item.get("measured_at") or ""), item["measurement_id"]),
    )


def _has_comparable_metric(measurement: ActionPlanMeasurement, metric_id: str) -> bool:
    baseline = _metric_by_id(measurement.baseline_metrics, metric_id)
    outcome = _metric_by_id(measurement.outcome_metrics, metric_id)
    return bool(
        baseline.get("status") == "available"
        and outcome.get("status") == "available"
        and baseline.get("value") is not None
        and outcome.get("value") is not None
        and outcome.get("comparison_requirements_met") is True
        and outcome.get("scope_matches") is not False
    )


def _metric_by_id(items: list | None, metric_id: str) -> dict[str, Any]:
    for raw in items or []:
        if isinstance(raw, dict) and str(raw.get("metric_id") or "") == metric_id:
            return dict(raw)
    return {}


def _frozen_distinct_outcomes(candidate: GovernedPolicyCandidate) -> list[dict[str, Any]]:
    raw = list((candidate.evidence_snapshot or {}).get("outcomes") or [])
    distinct: dict[str, dict[str, Any]] = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        measurement_id = str(item.get("measurement_id") or "").strip()
        classification = str(item.get("result_classification") or "").strip()
        if measurement_id and classification in {
            "improved",
            "about_the_same",
            "worse",
        }:
            distinct[measurement_id] = {
                "measurement_id": measurement_id,
                "result_classification": classification,
                "measured_at": item.get("measured_at"),
            }
    return sorted(
        distinct.values(),
        key=lambda item: (str(item.get("measured_at") or ""), item["measurement_id"]),
    )


def _evaluate_prefix(
    outcomes: list[dict[str, Any]],
    *,
    challenger_rule: dict[str, Any],
    protocol_completed: bool,
) -> dict[str, Any]:
    sample_count = len(outcomes)
    improved_count = sum(1 for item in outcomes if item["result_classification"] == "improved")
    worse_count = sum(1 for item in outcomes if item["result_classification"] == "worse")
    same_count = sample_count - improved_count - worse_count
    improvement_ratio = improved_count / sample_count if sample_count else 0.0
    worse_ratio = worse_count / sample_count if sample_count else 0.0
    improvement_interval = _wilson_interval(improved_count, sample_count)
    worse_interval = _wilson_interval(worse_count, sample_count)
    minimum_samples = int(challenger_rule.get("minimum_owner_included_matching_outcomes") or 10)
    checks = {
        "minimum_sample_met": sample_count >= minimum_samples,
        "completed_protocol_met": protocol_completed,
        "improvement_ratio_met": improvement_ratio
        >= float(challenger_rule.get("minimum_improvement_ratio") or 0.60),
        "worse_ratio_met": worse_ratio <= float(challenger_rule.get("maximum_worse_ratio") or 0.25),
        "improvement_wilson_lower_met": improvement_interval["lower"]
        >= float(challenger_rule.get("minimum_improvement_wilson_lower_90") or 0.35),
    }
    return {
        "prefix_size": sample_count,
        "sample_count": sample_count,
        "improved_count": improved_count,
        "about_the_same_count": same_count,
        "worse_count": worse_count,
        "improvement_ratio": round(improvement_ratio, 6),
        "worse_ratio": round(worse_ratio, 6),
        "improvement_wilson_90": improvement_interval,
        "worse_wilson_90": worse_interval,
        "checks": checks,
        "eligible": all(checks.values()),
    }


def _wilson_interval(successes: int, samples: int) -> dict[str, float]:
    if samples <= 0:
        return {"lower": 0.0, "upper": 1.0}
    proportion = successes / samples
    z_squared = WILSON_Z_90**2
    denominator = 1 + z_squared / samples
    center = proportion + z_squared / (2 * samples)
    margin = WILSON_Z_90 * math.sqrt(
        (proportion * (1 - proportion) + z_squared / (4 * samples)) / samples
    )
    return {
        "lower": round(max(0.0, (center - margin) / denominator), 6),
        "upper": round(min(1.0, (center + margin) / denominator), 6),
    }


def _empty_final_result() -> dict[str, Any]:
    return {
        "prefix_size": 0,
        "sample_count": 0,
        "improved_count": 0,
        "about_the_same_count": 0,
        "worse_count": 0,
        "improvement_ratio": 0.0,
        "worse_ratio": 0.0,
        "improvement_wilson_90": {"lower": 0.0, "upper": 1.0},
        "worse_wilson_90": {"lower": 0.0, "upper": 1.0},
        "checks": {},
        "eligible": False,
    }


def _verify_candidate_hash(candidate: GovernedPolicyCandidate) -> None:
    evidence_hash = _hash(dict(candidate.evidence_snapshot or {}))
    expected = _hash(
        {
            "candidate_version": candidate.candidate_version,
            "policy_family": candidate.policy_family,
            "protocol_id": candidate.protocol_id,
            "plan_id": candidate.plan_id,
            "protocol_hash": candidate.protocol_hash,
            "champion_rule": dict(candidate.champion_rule or {}),
            "challenger_rule": dict(candidate.challenger_rule or {}),
            "evidence_hash": evidence_hash,
        }
    )
    if evidence_hash != candidate.evidence_hash or expected != candidate.candidate_hash:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The saved rule candidate no longer matches its frozen evidence",
        )


def _verify_replay_hash(
    candidate: GovernedPolicyCandidate,
    replay: GovernedPolicyReplay,
) -> None:
    expected = _hash(
        {
            "replay_version": replay.replay_version,
            "candidate_hash": candidate.candidate_hash,
            "evidence_hash": candidate.evidence_hash,
            "ordered_measurement_ids": list(replay.ordered_measurement_ids or []),
            "cumulative_results": list(replay.cumulative_results or []),
            "final_result": dict(replay.final_result or {}),
        }
    )
    if (
        replay.candidate_hash != candidate.candidate_hash
        or replay.evidence_hash != candidate.evidence_hash
        or expected != replay.artifact_hash
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The replay no longer matches the exact frozen candidate",
        )


def _serialize_item(db: Session, candidate: GovernedPolicyCandidate) -> dict[str, Any]:
    replay = _latest_replay(db, candidate)
    decision = (
        db.query(GovernedPolicyDecision)
        .filter(
            GovernedPolicyDecision.candidate_id == candidate.id,
            GovernedPolicyDecision.tenant_id == candidate.tenant_id,
            GovernedPolicyDecision.organization_id == candidate.organization_id,
        )
        .first()
    )
    state = _state(replay, decision)
    return {
        **_serialize_candidate(candidate),
        "latest_replay": _serialize_replay(replay) if replay is not None else None,
        "decision": _serialize_decision(decision) if decision is not None else None,
        "state": state,
        "plain_language": _plain_language(candidate, replay, decision, state),
        "safety": _safety(),
    }


def _serialize_candidate(row: GovernedPolicyCandidate) -> dict[str, Any]:
    snapshot = dict(row.evidence_snapshot or {})
    return {
        "id": row.id,
        "source_protocol_id": row.protocol_id,
        "source_plan_id": row.plan_id,
        "campaign_id": row.campaign_id,
        "business_location_id": row.business_location_id,
        "policy_family": row.policy_family,
        "action_id": snapshot.get("action_id"),
        "metric_id": snapshot.get("metric_id"),
        "measurement_contract_version": snapshot.get("measurement_contract_version"),
        "champion_version": "current-1.0",
        "champion_rules": _serialize_rules(dict(row.champion_rule or {})),
        "challenger_version": row.candidate_version,
        "challenger_rules": _serialize_rules(dict(row.challenger_rule or {})),
        "distinct_measurement_count": snapshot.get("distinct_measurement_count", 0),
        "protocol_status": snapshot.get("protocol_status"),
        "evidence_hash": row.evidence_hash,
        "protocol_hash": row.protocol_hash,
        "candidate_hash": row.candidate_hash,
        "created_at": _iso(row.created_at),
        "automatic_activation_allowed": bool(row.automatic_activation_allowed),
        "immutable": True,
    }


def _serialize_replay(row: GovernedPolicyReplay) -> dict[str, Any]:
    final = dict(row.final_result or {})
    prefixes = list(row.cumulative_results or [])
    checks = dict(final.get("checks") or {})
    return {
        "id": row.id,
        "status": row.status,
        "replay_version": row.replay_version,
        "independent_sample_size": int(final.get("sample_count") or 0),
        "improved_count": int(final.get("improved_count") or 0),
        "unchanged_count": int(final.get("about_the_same_count") or 0),
        "worse_count": int(final.get("worse_count") or 0),
        "improvement_ratio": float(final.get("improvement_ratio") or 0.0),
        "worse_ratio": float(final.get("worse_ratio") or 0.0),
        "final_champion_eligible": int(final.get("sample_count") or 0) >= CHAMPION_MINIMUM_OUTCOMES,
        "final_challenger_eligible": bool(final.get("eligible")),
        "changed_decision_count": sum(
            1
            for item in prefixes
            if (int(item.get("sample_count") or 0) >= CHAMPION_MINIMUM_OUTCOMES)
            != bool(item.get("eligible"))
        ),
        "blockers": _replay_blockers(checks),
        "candidate_hash": row.candidate_hash,
        "evidence_hash": row.evidence_hash,
        "ordered_measurement_ids": list(row.ordered_measurement_ids or []),
        "cumulative_results": prefixes,
        "final_result": final,
        "artifact_hash": row.artifact_hash,
        "created_at": _iso(row.replayed_at),
        "replayed_at": _iso(row.replayed_at),
        "automatic_activation_allowed": bool(row.automatic_activation_allowed),
        "immutable": True,
    }


def _serialize_decision(row: GovernedPolicyDecision) -> dict[str, Any]:
    return {
        "id": row.id,
        "decision": row.decision,
        "replay_id": row.replay_id,
        "acknowledgements": dict(row.acknowledgements or {}),
        "note": row.review_note,
        "candidate_hash": row.candidate_hash,
        "replay_artifact_hash": row.replay_artifact_hash,
        "decision_hash": row.decision_hash,
        "reviewed_at": _iso(row.decided_at),
        "decided_at": _iso(row.decided_at),
        "automatic_activation_allowed": bool(row.automatic_activation_allowed),
        "immutable": True,
    }


def _serialize_rules(rule: dict[str, Any]) -> dict[str, Any]:
    minimum = rule.get("minimum_owner_included_matching_outcomes")
    return {
        "minimum_independent_results": minimum,
        "minimum_sample_size": minimum,
        "minimum_improvement_ratio": rule.get("minimum_improvement_ratio"),
        "maximum_worse_ratio": rule.get("maximum_worse_ratio"),
        "minimum_improvement_wilson_lower_bound": rule.get("minimum_improvement_wilson_lower_90"),
        "requires_completed_protocol": bool(rule.get("completed_protocol_required")),
    }


def _replay_blockers(checks: dict[str, Any]) -> list[dict[str, str]]:
    labels = {
        "minimum_sample_met": (
            "needs_more_independent_results",
            "More independent, owner-approved matching results are needed.",
        ),
        "completed_protocol_met": (
            "completed_protocol_required",
            "The controlled test must be completed first.",
        ),
        "improvement_ratio_met": (
            "improvement_ratio_too_low",
            "Too few of the matching results improved for the stricter rule.",
        ),
        "worse_ratio_met": (
            "worse_ratio_too_high",
            "Too many of the matching results got worse for the stricter rule.",
        ),
        "improvement_wilson_lower_met": (
            "confidence_check_not_met",
            "The saved confidence check needs stronger improvement evidence.",
        ),
    }
    return [
        {"code": labels[key][0], "message": labels[key][1]}
        for key, passed in checks.items()
        if passed is not True and key in labels
    ]


def _state(
    replay: GovernedPolicyReplay | None,
    decision: GovernedPolicyDecision | None,
) -> str:
    if decision is not None:
        return decision.decision
    if replay is None:
        return "needs_replay"
    if replay.status == "passed":
        return "ready_for_human_review"
    return "replay_did_not_pass"


def _plain_language(
    candidate: GovernedPolicyCandidate,
    replay: GovernedPolicyReplay | None,
    decision: GovernedPolicyDecision | None,
    state: str,
) -> dict[str, str]:
    count = int((candidate.evidence_snapshot or {}).get("distinct_measurement_count") or 0)
    if decision is not None and decision.decision == "approved_for_future_activation":
        next_step = (
            "This only saves approval for a later release. A separate future approval "
            "is still required before any rule can change."
        )
    elif decision is not None:
        next_step = "No rule will change from this candidate."
    elif replay is None:
        next_step = "Run the saved replay to check the stricter rule against every result in order."
    elif replay.status == "passed":
        next_step = "Review the exact passing replay. Approval still will not change a live rule."
    else:
        next_step = "Keep the current rule. This stricter rule did not pass every saved check."
    return {
        "title": "Check whether learning should require stronger proof",
        "summary": (
            f"This candidate compares the current five-result rule with a stricter rule "
            f"using {count} owner-approved matching results."
        ),
        "state": state.replace("_", " "),
        "next_step": next_step,
    }


def _latest_replay(
    db: Session,
    candidate: GovernedPolicyCandidate,
) -> GovernedPolicyReplay | None:
    return (
        db.query(GovernedPolicyReplay)
        .filter(
            GovernedPolicyReplay.candidate_id == candidate.id,
            GovernedPolicyReplay.tenant_id == candidate.tenant_id,
            GovernedPolicyReplay.organization_id == candidate.organization_id,
        )
        .order_by(
            GovernedPolicyReplay.replayed_at.desc(),
            GovernedPolicyReplay.id.desc(),
        )
        .first()
    )


def _campaign_or_404(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
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
) -> GovernedExperimentProtocol:
    _campaign_or_404(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=campaign_id,
    )
    row = (
        db.query(GovernedExperimentProtocol)
        .filter(
            GovernedExperimentProtocol.id == protocol_id,
            GovernedExperimentProtocol.tenant_id == tenant_id,
            GovernedExperimentProtocol.organization_id == organization_id,
            GovernedExperimentProtocol.campaign_id == campaign_id,
        )
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Controlled-test monitoring protocol not found")
    return row


def _candidate_or_404(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
    candidate_id: str,
    lock_for_update: bool = False,
) -> GovernedPolicyCandidate:
    _campaign_or_404(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=campaign_id,
    )
    query = db.query(GovernedPolicyCandidate).filter(
        GovernedPolicyCandidate.id == candidate_id,
        GovernedPolicyCandidate.tenant_id == tenant_id,
        GovernedPolicyCandidate.organization_id == organization_id,
        GovernedPolicyCandidate.campaign_id == campaign_id,
        GovernedPolicyCandidate.policy_family == POLICY_FAMILY,
    )
    if lock_for_update:
        query = query.with_for_update()
    row = query.first()
    if row is None:
        raise HTTPException(status_code=404, detail="Rule candidate not found")
    return row


def _replay_or_404(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
    candidate_id: str,
    replay_id: str,
) -> GovernedPolicyReplay:
    row = (
        db.query(GovernedPolicyReplay)
        .filter(
            GovernedPolicyReplay.id == replay_id,
            GovernedPolicyReplay.candidate_id == candidate_id,
            GovernedPolicyReplay.tenant_id == tenant_id,
            GovernedPolicyReplay.organization_id == organization_id,
            GovernedPolicyReplay.campaign_id == campaign_id,
        )
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Exact replay not found")
    return row


def _audit(
    db: Session,
    *,
    row: GovernedPolicyCandidate,
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
            "candidate_id": row.id,
            "policy_family": row.policy_family,
            "candidate_hash": row.candidate_hash,
            **_safety(),
            **extra,
        },
    )


def _safety() -> dict[str, bool]:
    return {
        "candidate_only": True,
        "active_policy_changed": False,
        "automatic_activation_allowed": False,
        "legacy_policy_weights_changed": False,
        "legacy_experiment_connected": False,
        "automatic_policy_updates_enabled": False,
        "live_policy_activation_enabled": False,
        "live_policy_changed": False,
        "execution_enabled": False,
        "assignments_created": False,
        "publishing_enabled": False,
        "wordpress_changes_enabled": False,
        "standards_activation_enabled": False,
        "automatic_rollback_enabled": False,
    }


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None

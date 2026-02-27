from __future__ import annotations

import hashlib
import json
import os
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.governance.replay.hashing import version_fingerprint
from app.models.campaign import Campaign
from app.models.intelligence import StrategyRecommendation
from app.models.strategy_automation_event import StrategyAutomationEvent
from app.models.temporal import MomentumMetric, StrategyPhaseHistory
from app.observability.events import emit_automation_event, emit_phase_transition, emit_rule_trigger
from app.services.strategy_engine.decision_trace import build_decision_trace, serialize_trace_payload

AUTOMATION_ENGINE_VERSION = 'automation-loop-v1'
FREEZE_VOLATILITY_CEILING = 0.9
PROMOTION_CONFIDENCE_THRESHOLD = 0.8
NEGATIVE_MOMENTUM_THRESHOLD = -0.2
POSITIVE_MOMENTUM_THRESHOLD = 0.2
DOMINANCE_MOMENTUM_THRESHOLD = 0.55
DECISION_PRECISION = 6


def _month_anchor(evaluation_date: datetime) -> datetime:
    return datetime(evaluation_date.year, evaluation_date.month, 1, tzinfo=UTC)


def _manual_lock_active(campaign: Campaign) -> bool:
    return bool(campaign.manual_automation_lock)


def _guardrails(campaign: Campaign, metrics: list[MomentumMetric]) -> list[str]:
    rules: list[str] = []
    if len(metrics) < 3:
        rules.append('insufficient_historical_window')
    if metrics and float(metrics[0].volatility) >= FREEZE_VOLATILITY_CEILING:
        rules.append('freeze_high_volatility')
    if _manual_lock_active(campaign):
        rules.append('manual_lock_mode')
    if os.getenv('LSOS_REPLAY_MODE', '0').strip() == '1' or os.getenv('REPLAY_MODE', '0').strip() == '1':
        rules.append('replay_mode_active')
    return rules


def _phase_decision(momentum_score: float, slope: float, volatility: float) -> tuple[str, list[str]]:
    rules: list[str] = []
    if volatility >= FREEZE_VOLATILITY_CEILING:
        rules.append('volatility_above_freeze_ceiling')
        return 'stabilization', rules
    if slope >= 0.08 or momentum_score <= NEGATIVE_MOMENTUM_THRESHOLD:
        rules.append('sustained_negative_slope')
        return 'recovery', rules
    if momentum_score >= DOMINANCE_MOMENTUM_THRESHOLD:
        rules.append('dominance_threshold_reached')
        return 'acceleration', rules
    if momentum_score >= POSITIVE_MOMENTUM_THRESHOLD:
        rules.append('sustained_positive_slope')
        return 'growth', rules
    rules.append('default_stabilization_band')
    return 'stabilization', rules


def _opportunity_score(rec: StrategyRecommendation) -> float:
    risk_norm = max(0.0, min(1.0, 1.0 - (float(rec.risk_tier) / 4.0)))
    return max(0.0, float(rec.confidence_score) * risk_norm)


def _normalize_allocation(momentum_score: float, recs: list[StrategyRecommendation]) -> dict[str, float]:
    raw: dict[str, float] = {}
    for rec in recs:
        raw_weight = max(0.0, momentum_score) * _opportunity_score(rec)
        raw[rec.id] = round(raw_weight, DECISION_PRECISION)
    total = sum(raw.values())
    if total <= 0:
        return {rec_id: 0.0 for rec_id in raw}
    return {rec_id: round(weight / total, DECISION_PRECISION) for rec_id, weight in raw.items()}


def _adjust_recommendations(momentum_score: float, recs: list[StrategyRecommendation]) -> list[dict[str, str]]:
    transitions: list[dict[str, str]] = []
    by_type_failed = Counter(rec.recommendation_type for rec in recs if rec.status == 'FAILED')

    for rec in recs:
        from_state = rec.status
        to_state = from_state
        if from_state == 'GENERATED' and rec.confidence_score >= PROMOTION_CONFIDENCE_THRESHOLD and momentum_score > POSITIVE_MOMENTUM_THRESHOLD:
            to_state = 'VALIDATED'
        elif from_state in {'GENERATED', 'VALIDATED'} and by_type_failed.get(rec.recommendation_type, 0) >= 2:
            to_state = 'ARCHIVED'
        elif from_state in {'GENERATED', 'VALIDATED'} and momentum_score < NEGATIVE_MOMENTUM_THRESHOLD:
            to_state = 'ARCHIVED'

        if to_state != from_state:
            rec.status = to_state
            transitions.append({'recommendation_id': rec.id, 'from': from_state, 'to': to_state})

    transitions.sort(key=lambda item: (item['recommendation_id'], item['from'], item['to']))
    return transitions


def _canonicalize_payload(payload: Any) -> Any:
    if isinstance(payload, float):
        return round(payload, DECISION_PRECISION)
    if isinstance(payload, dict):
        return {key: _canonicalize_payload(payload[key]) for key in sorted(payload)}
    if isinstance(payload, list):
        return [_canonicalize_payload(item) for item in payload]
    return payload


def _json_payload(payload: Any) -> str:
    return json.dumps(_canonicalize_payload(payload), sort_keys=True, separators=(',', ':'))


def _decision_hash(
    *,
    campaign_id: str,
    evaluation_month: str,
    prior_phase: str,
    new_phase: str,
    triggered_rules: list[str],
    recommendation_ids: list[str],
    momentum_snapshot: dict[str, Any],
    action_snapshot: dict[str, Any],
) -> str:
    digest_payload = {
        'automation_engine_version': AUTOMATION_ENGINE_VERSION,
        'campaign_id': campaign_id,
        'evaluation_month': evaluation_month,
        'prior_phase': prior_phase,
        'new_phase': new_phase,
        'triggered_rules': sorted(triggered_rules),
        'recommendation_ids': sorted(recommendation_ids),
        'momentum_snapshot': _canonicalize_payload(momentum_snapshot),
        'action_snapshot': _canonicalize_payload(action_snapshot),
    }
    packed = json.dumps(digest_payload, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(packed.encode('utf-8')).hexdigest()


def _safe_emit(func: Any, **kwargs: Any) -> None:
    try:
        func(**kwargs)
    except Exception:
        return


def evaluate_campaign_for_automation(campaign_id: str, db: Session, evaluation_date: datetime | None = None) -> dict:
    now = evaluation_date or datetime.now(UTC)
    cycle_anchor = _month_anchor(now)

    existing = (
        db.query(StrategyAutomationEvent)
        .filter(
            StrategyAutomationEvent.campaign_id == campaign_id,
            StrategyAutomationEvent.evaluation_date == cycle_anchor,
        )
        .first()
    )
    if existing is not None:
        _safe_emit(
            emit_automation_event,
            campaign_id=campaign_id,
            evaluation_date=cycle_anchor.isoformat(),
            status='already_evaluated',
            decision_hash=existing.decision_hash,
        )
        return {
            'campaign_id': campaign_id,
            'status': 'already_evaluated',
            'evaluation_date': cycle_anchor.isoformat(),
            'event_id': existing.id,
        }

    campaign = db.get(Campaign, campaign_id)
    if campaign is None:
        return {'campaign_id': campaign_id, 'status': 'campaign_not_found'}

    metrics = (
        db.query(MomentumMetric)
        .filter(MomentumMetric.campaign_id == campaign_id)
        .order_by(MomentumMetric.computed_at.desc(), MomentumMetric.id.desc())
        .limit(6)
        .all()
    )
    guardrail_hits = _guardrails(campaign, metrics)

    latest_phase = (
        db.query(StrategyPhaseHistory)
        .filter(StrategyPhaseHistory.campaign_id == campaign_id)
        .order_by(StrategyPhaseHistory.effective_date.desc(), StrategyPhaseHistory.id.desc())
        .first()
    )
    prior_phase = latest_phase.new_phase if latest_phase is not None else 'stabilization'

    recs = (
        db.query(StrategyRecommendation)
        .filter(
            StrategyRecommendation.campaign_id == campaign_id,
            StrategyRecommendation.status.in_({'GENERATED', 'VALIDATED', 'FAILED'}),
        )
        .order_by(StrategyRecommendation.created_at.desc(), StrategyRecommendation.id.desc())
        .all()
    )

    rule_evaluations: list[dict[str, Any]] = []
    if guardrail_hits:
        new_phase = prior_phase
        triggered_rules = guardrail_hits
        momentum_score = 0.0
        slope = 0.0
        volatility = float(metrics[0].volatility) if metrics else 0.0
        transitions: list[dict[str, str]] = []
        allocation = {rec.id: 0.0 for rec in recs}
        status = 'frozen'
        for rule in guardrail_hits:
            rule_evaluations.append({'rule': rule, 'result': True, 'source': 'guardrail'})
    else:
        latest = metrics[0]
        slope = float(latest.slope)
        volatility = float(latest.volatility)
        momentum_score = max(-1.0, min(1.0, (-slope) * (1.0 - min(volatility, 1.0))))
        new_phase, triggered_rules = _phase_decision(momentum_score=momentum_score, slope=slope, volatility=volatility)
        transitions = _adjust_recommendations(momentum_score=momentum_score, recs=recs)
        allocation = _normalize_allocation(momentum_score=momentum_score, recs=recs)
        status = 'evaluated'
        for rule in triggered_rules:
            rule_evaluations.append({'rule': rule, 'result': True, 'source': 'phase_decision'})

    action_summary = {
        'recommendation_transitions': transitions,
        'allocation_weights': allocation,
        'recommendation_count': len(recs),
        'status': status,
    }
    momentum_snapshot = {
        'momentum_score': round(momentum_score, DECISION_PRECISION),
        'slope': round(slope, DECISION_PRECISION),
        'volatility': round(volatility, DECISION_PRECISION),
        'metrics_considered': len(metrics),
    }

    recommendation_ids = sorted(rec.id for rec in recs)
    decision_hash = _decision_hash(
        campaign_id=campaign_id,
        evaluation_month=cycle_anchor.date().isoformat(),
        prior_phase=prior_phase,
        new_phase=new_phase,
        triggered_rules=triggered_rules,
        recommendation_ids=recommendation_ids,
        momentum_snapshot=momentum_snapshot,
        action_snapshot=action_summary,
    )

    decision_trace = build_decision_trace(
        rule_evaluations=rule_evaluations,
        threshold_values={
            'freeze_volatility_ceiling': FREEZE_VOLATILITY_CEILING,
            'promotion_confidence_threshold': PROMOTION_CONFIDENCE_THRESHOLD,
            'negative_momentum_threshold': NEGATIVE_MOMENTUM_THRESHOLD,
            'positive_momentum_threshold': POSITIVE_MOMENTUM_THRESHOLD,
            'dominance_momentum_threshold': DOMINANCE_MOMENTUM_THRESHOLD,
        },
        momentum_inputs=momentum_snapshot,
        volatility_inputs={'volatility': momentum_snapshot['volatility']},
        allocation_weights=allocation,
        confidence_adjustments=[
            {
                'recommendation_id': transition['recommendation_id'],
                'from': transition['from'],
                'to': transition['to'],
            }
            for transition in transitions
        ],
    )

    version_hash = version_fingerprint(
        {
            'engine_version': AUTOMATION_ENGINE_VERSION,
            'campaign_id': campaign_id,
            'evaluation_date': cycle_anchor.isoformat(),
            'prior_phase': prior_phase,
            'new_phase': new_phase,
            'triggered_rules': triggered_rules,
            'momentum_snapshot': momentum_snapshot,
            'action_summary': action_summary,
            'decision_hash': decision_hash,
            'trace_payload': decision_trace,
        }
    )

    event = StrategyAutomationEvent(
        campaign_id=campaign_id,
        evaluation_date=cycle_anchor,
        prior_phase=prior_phase,
        new_phase=new_phase,
        triggered_rules=json.dumps(sorted(triggered_rules), sort_keys=True),
        momentum_snapshot=_json_payload(momentum_snapshot),
        action_summary=_json_payload(action_summary),
        trace_payload=serialize_trace_payload(decision_trace),
        decision_hash=decision_hash,
        version_hash=version_hash,
    )
    db.add(event)

    if not guardrail_hits and new_phase != prior_phase:
        db.add(
            StrategyPhaseHistory(
                campaign_id=campaign_id,
                prior_phase=prior_phase,
                new_phase=new_phase,
                trigger_reason='automation_engine_rule_transition',
                momentum_score=momentum_snapshot['momentum_score'],
                effective_date=cycle_anchor,
                version_hash=version_hash,
            )
        )

    db.commit()
    db.refresh(event)

    _safe_emit(emit_rule_trigger, campaign_id=campaign_id, triggered_rules=triggered_rules, decision_hash=decision_hash)
    _safe_emit(
        emit_automation_event,
        campaign_id=campaign_id,
        evaluation_date=cycle_anchor.isoformat(),
        status=status,
        decision_hash=decision_hash,
    )
    if not guardrail_hits and new_phase != prior_phase:
        _safe_emit(
            emit_phase_transition,
            campaign_id=campaign_id,
            prior_phase=prior_phase,
            new_phase=new_phase,
            decision_hash=decision_hash,
        )

    return {
        'campaign_id': campaign_id,
        'status': status,
        'evaluation_date': cycle_anchor.isoformat(),
        'prior_phase': prior_phase,
        'new_phase': new_phase,
        'triggered_rules': triggered_rules,
        'momentum_snapshot': momentum_snapshot,
        'decision_hash': decision_hash,
        'event_id': event.id,
        'action_summary': action_summary,
    }
from __future__ import annotations

import json
import os
from collections import Counter
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.governance.replay.hashing import version_fingerprint
from app.models.campaign import Campaign
from app.models.intelligence import StrategyRecommendation
from app.models.strategy_automation_event import StrategyAutomationEvent
from app.models.temporal import MomentumMetric, StrategyPhaseHistory

AUTOMATION_ENGINE_VERSION = 'automation-loop-v1'
FREEZE_VOLATILITY_CEILING = 0.9
PROMOTION_CONFIDENCE_THRESHOLD = 0.8
NEGATIVE_MOMENTUM_THRESHOLD = -0.2
POSITIVE_MOMENTUM_THRESHOLD = 0.2
DOMINANCE_MOMENTUM_THRESHOLD = 0.55


def _month_anchor(evaluation_date: datetime) -> datetime:
    return datetime(evaluation_date.year, evaluation_date.month, 1, tzinfo=UTC)


def _manual_lock_active(campaign: Campaign) -> bool:
    state = (campaign.setup_state or '').strip().lower()
    return state in {'manual_lock', 'manual-lock', 'manuallock'}


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
    # Dominance-level momentum still maps to acceleration in phase-3 rules.
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
        raw[rec.id] = round(raw_weight, 6)
    total = sum(raw.values())
    if total <= 0:
        return {rec_id: 0.0 for rec_id in raw}
    return {rec_id: round(weight / total, 6) for rec_id, weight in raw.items()}


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

    return transitions


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

    if guardrail_hits:
        new_phase = prior_phase
        triggered_rules = guardrail_hits
        momentum_score = 0.0
        slope = 0.0
        volatility = float(metrics[0].volatility) if metrics else 0.0
        transitions: list[dict[str, str]] = []
        allocation = {rec.id: 0.0 for rec in recs}
        status = 'frozen'
    else:
        latest = metrics[0]
        slope = float(latest.slope)
        volatility = float(latest.volatility)
        momentum_score = max(-1.0, min(1.0, (-slope) * (1.0 - min(volatility, 1.0))))
        new_phase, triggered_rules = _phase_decision(momentum_score=momentum_score, slope=slope, volatility=volatility)
        transitions = _adjust_recommendations(momentum_score=momentum_score, recs=recs)
        allocation = _normalize_allocation(momentum_score=momentum_score, recs=recs)
        status = 'evaluated'

    action_summary = {
        'recommendation_transitions': transitions,
        'allocation_weights': allocation,
        'recommendation_count': len(recs),
        'status': status,
    }
    momentum_snapshot = {
        'momentum_score': round(momentum_score, 6),
        'slope': round(slope, 6),
        'volatility': round(volatility, 6),
        'metrics_considered': len(metrics),
    }

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
        }
    )

    event = StrategyAutomationEvent(
        campaign_id=campaign_id,
        evaluation_date=cycle_anchor,
        prior_phase=prior_phase,
        new_phase=new_phase,
        triggered_rules=json.dumps(triggered_rules, sort_keys=True),
        momentum_snapshot=json.dumps(momentum_snapshot, sort_keys=True),
        action_summary=json.dumps(action_summary, sort_keys=True),
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

    return {
        'campaign_id': campaign_id,
        'status': status,
        'evaluation_date': cycle_anchor.isoformat(),
        'prior_phase': prior_phase,
        'new_phase': new_phase,
        'triggered_rules': triggered_rules,
        'momentum_snapshot': momentum_snapshot,
        'event_id': event.id,
        'action_summary': action_summary,
    }

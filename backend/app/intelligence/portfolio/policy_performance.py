from __future__ import annotations

import json
from math import tanh
from typing import Any

from sqlalchemy.orm import Session

from app.models.campaign import Campaign
from app.models.intelligence import StrategyRecommendation
from app.models.policy_performance import PolicyPerformance
from app.models.recommendation_outcome import RecommendationOutcome


def derive_policy_id(recommendation: StrategyRecommendation) -> str:
    evidence = _parse_json(recommendation.evidence_json)
    policy_id = str(evidence.get('policy_id') or '').strip()
    if policy_id:
        return policy_id

    recommendation_type = str(recommendation.recommendation_type or '').strip()
    if recommendation_type.startswith('policy::'):
        parts = recommendation_type.split('::')
        if len(parts) >= 2 and parts[1]:
            return parts[1]
    if recommendation_type.startswith('transfer::'):
        return 'transfer_engine'
    return 'unknown_policy'


def update_policy_performance(db: Session, outcome: RecommendationOutcome) -> PolicyPerformance | None:
    recommendation = db.get(StrategyRecommendation, outcome.recommendation_id)
    if recommendation is None:
        return None

    campaign = db.get(Campaign, outcome.campaign_id)
    industry = _campaign_industry(campaign, recommendation)
    policy_id = derive_policy_id(recommendation)
    reward = _success_score(outcome.metric_before, outcome.metric_after)

    row = (
        db.query(PolicyPerformance)
        .filter(
            PolicyPerformance.policy_id == policy_id,
            PolicyPerformance.campaign_id == outcome.campaign_id,
            PolicyPerformance.industry == industry,
        )
        .first()
    )
    if row is None:
        row = PolicyPerformance(
            policy_id=policy_id,
            campaign_id=outcome.campaign_id,
            industry=industry,
            success_score=reward,
            execution_count=1,
            confidence=_confidence_for_count(1),
        )
        db.add(row)
        db.flush()
        return row

    previous_count = int(row.execution_count)
    next_count = previous_count + 1
    row.success_score = round(((row.success_score * previous_count) + reward) / next_count, 6)
    row.execution_count = next_count
    row.confidence = _confidence_for_count(next_count)
    db.flush()
    return row


def _campaign_industry(campaign: Campaign | None, recommendation: StrategyRecommendation) -> str:
    if campaign is not None and campaign.portfolio_id:
        return str(campaign.portfolio_id)
    evidence = _parse_json(recommendation.evidence_json)
    industry = evidence.get('industry') or evidence.get('industry_id')
    if isinstance(industry, str) and industry.strip():
        return industry.strip()
    return 'unknown'


def _success_score(metric_before: float, metric_after: float) -> float:
    before = float(metric_before)
    after = float(metric_after)
    if before == 0.0:
        return round(max(-1.0, min(1.0, after)), 6)
    delta_ratio = (after - before) / abs(before)
    return round(max(-1.0, min(1.0, tanh(delta_ratio))), 6)


def _confidence_for_count(execution_count: int) -> float:
    return round(min(1.0, max(0.1, execution_count / 10.0)), 6)


def _parse_json(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}

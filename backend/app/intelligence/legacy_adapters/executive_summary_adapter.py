from __future__ import annotations

import json
from typing import Any

from app.models.intelligence import StrategyRecommendation
from app.services.strategy_engine.executive_summary import build_executive_summary
from app.services.strategy_engine.scenario_registry import SCENARIO_INDEX
from app.services.strategy_engine.schemas import CampaignStrategyOut, StrategyRecommendationOut, StrategyWindow
from app.services.strategy_engine.strategic_scoring import compute_strategic_scores


def build_legacy_packaging(
    *,
    campaign_id: str,
    tier: str,
    window: StrategyWindow,
    recommendations: list[StrategyRecommendation],
    detected_scenarios: list[str],
    generated_at: str,
) -> dict[str, Any]:
    out = CampaignStrategyOut(
        campaign_id=campaign_id,
        window=window,
        detected_scenarios=sorted(set(detected_scenarios)),
        recommendations=_to_legacy_recommendations(recommendations),
        meta={
            'tier': tier,
            'engine_version': 'modern-intelligence-with-legacy-packaging-v1',
            'generated_at': generated_at,
        },
    )
    out.strategic_scores = compute_strategic_scores(out)
    out.executive_summary = build_executive_summary(out)
    return {
        'strategic_scores': out.strategic_scores.model_dump(),
        'executive_summary': out.executive_summary.model_dump(),
        'detected_scenarios': out.detected_scenarios,
        'operator_explanations': [_operator_explanation(rec) for rec in recommendations],
    }


def _to_legacy_recommendations(recommendations: list[StrategyRecommendation]) -> list[StrategyRecommendationOut]:
    items: list[StrategyRecommendationOut] = []
    for rec in recommendations:
        evidence_payload = _parse_json(rec.evidence_json)
        scenario_id = str(evidence_payload.get('legacy_source_scenario_id') or _scenario_from_recommendation_type(rec.recommendation_type) or '')
        scenario = SCENARIO_INDEX.get(scenario_id)
        if scenario is None:
            continue
        operator = evidence_payload.get('operator_explanation') if isinstance(evidence_payload.get('operator_explanation'), dict) else {}
        evidence = operator.get('evidence') if isinstance(operator.get('evidence'), list) else []
        items.append(
            StrategyRecommendationOut(
                scenario_id=scenario_id,
                priority_score=float(rec.confidence_score or rec.confidence or 0.0),
                diagnosis=str(operator.get('diagnosis') or scenario.diagnosis),
                root_cause=str(operator.get('root_cause') or scenario.root_cause),
                recommended_actions=list(scenario.recommended_actions),
                expected_outcome=str(operator.get('expected_outcome') or scenario.expected_outcome),
                authoritative_sources=list(operator.get('authoritative_sources') or scenario.authoritative_sources),
                confidence=float(rec.confidence or 0.0),
                impact_level=str(operator.get('impact_level') or scenario.impact_level),
                evidence=evidence,
            )
        )
    return items


def _operator_explanation(rec: StrategyRecommendation) -> dict[str, Any]:
    evidence_payload = _parse_json(rec.evidence_json)
    operator = evidence_payload.get('operator_explanation') if isinstance(evidence_payload.get('operator_explanation'), dict) else {}
    return {
        'recommendation_id': rec.id,
        'recommendation_type': rec.recommendation_type,
        'scenario_id': evidence_payload.get('legacy_source_scenario_id'),
        'diagnosis': operator.get('diagnosis'),
        'root_cause': operator.get('root_cause'),
        'expected_outcome': operator.get('expected_outcome'),
        'impact_level': operator.get('impact_level'),
    }


def _parse_json(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _scenario_from_recommendation_type(recommendation_type: str) -> str | None:
    parts = recommendation_type.split('::')
    if len(parts) >= 4 and parts[0] == 'policy' and parts[1] == 'legacy':
        return parts[2]
    if len(parts) >= 3 and parts[0] == 'legacy':
        return parts[1]
    return None

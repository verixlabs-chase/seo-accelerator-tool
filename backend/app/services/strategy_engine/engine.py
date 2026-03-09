from __future__ import annotations


from typing import Any

from sqlalchemy.orm import Session

from app.intelligence.digital_twin.strategy_optimizer import optimize_strategy
from app.intelligence.digital_twin.twin_state_model import DigitalTwinState
from app.intelligence.feature_aggregator import describe_campaign_cohort
from app.models.strategy_cohort_pattern import StrategyCohortPattern
from app.models.strategy_memory_pattern import StrategyMemoryPattern
from app.services.strategy_engine.executive_summary import build_executive_summary
from app.services.strategy_engine.modules.competitor_diagnostics import run_competitor_diagnostics
from app.services.strategy_engine.modules.core_web_vitals_diagnostics import run_core_web_vitals_diagnostics
from app.services.strategy_engine.modules.ctr_diagnostics import run_ctr_diagnostics
from app.services.strategy_engine.modules.gbp_diagnostics import run_gbp_diagnostics
from app.services.strategy_engine.modules.ranking_diagnostics import run_ranking_diagnostics
from app.services.strategy_engine.modules.temporal_diagnostics import run_temporal_diagnostics
from app.services.strategy_engine.priority_engine import PriorityInput, rank_priorities
from app.services.strategy_engine.scenario_registry import SCENARIO_INDEX
from app.services.strategy_engine.schemas import CampaignStrategyOut, DiagnosticResult, StrategyRecommendationOut, StrategyWindow
from app.services.strategy_engine.signal_models import build_signal_model
from app.services.strategy_engine.strategic_scoring import compute_strategic_scores


DEPRECATED_RUNTIME = True
def build_campaign_strategy(
    campaign_id: str,
    window: StrategyWindow,
    raw_signals: dict[str, Any],
    tier: str,
    db: Session | None = None,
) -> CampaignStrategyOut:
    signals = build_signal_model(raw_signals)
    window_reference = f'{window.date_from.isoformat()}__{window.date_to.isoformat()}'

    diagnostics: list[DiagnosticResult] = []
    diagnostics.extend(run_ctr_diagnostics(signals, window_reference=window_reference, tier=tier))
    diagnostics.extend(run_core_web_vitals_diagnostics(signals, window_reference=window_reference))
    diagnostics.extend(run_ranking_diagnostics(signals, window_reference=window_reference))
    diagnostics.extend(run_gbp_diagnostics(signals, window_reference=window_reference, tier=tier))

    if tier == 'enterprise':
        diagnostics.extend(run_competitor_diagnostics(signals, window_reference=window_reference))

    if db is not None:
        diagnostics.extend(
            run_temporal_diagnostics(
                db,
                campaign_id=campaign_id,
                window=window,
                window_reference=window_reference,
                tier=tier,
            )
        )

    pattern_multiplier_by_feature = _cohort_pattern_multiplier_by_feature(db, campaign_id) if db is not None else {}
    memory_multiplier_by_feature = _strategy_memory_multiplier_by_feature(db, campaign_id) if db is not None else {}

    priority_inputs: list[PriorityInput] = []
    filtered_results: list[DiagnosticResult] = []
    for result in diagnostics:
        scenario = SCENARIO_INDEX.get(result.scenario_id)
        if scenario is None or scenario.deprecated:
            continue
        filtered_results.append(result)

        feature_name = _scenario_feature_name(result.scenario_id, scenario.category)
        cohort_multiplier = float(pattern_multiplier_by_feature.get(feature_name, 1.0))
        memory_multiplier = float(memory_multiplier_by_feature.get(feature_name, 1.0))
        multiplier = cohort_multiplier * memory_multiplier

        adjusted_impact_weight = max(0.0, min(1.0, scenario.impact_weight * multiplier))

        priority_inputs.append(
            PriorityInput(
                scenario_id=result.scenario_id,
                impact_weight=adjusted_impact_weight,
                signal_magnitude=result.signal_magnitude,
                confidence=result.confidence,
            )
        )

    ranked = rank_priorities(priority_inputs)
    result_by_id = {item.scenario_id: item for item in filtered_results}
    recommendations: list[StrategyRecommendationOut] = []
    for item in ranked:
        scenario = SCENARIO_INDEX[item.scenario_id]
        diagnostic = result_by_id[item.scenario_id]
        recommendations.append(
            StrategyRecommendationOut(
                scenario_id=scenario.scenario_id,
                priority_score=item.priority_score,
                diagnosis=scenario.diagnosis,
                root_cause=scenario.root_cause,
                recommended_actions=scenario.recommended_actions,
                expected_outcome=scenario.expected_outcome,
                authoritative_sources=scenario.authoritative_sources,
                confidence=diagnostic.confidence,
                impact_level=scenario.impact_level,
                evidence=diagnostic.evidence,
            )
        )

    output = CampaignStrategyOut(
        campaign_id=campaign_id,
        window=window,
        detected_scenarios=[item.scenario_id for item in ranked],
        recommendations=recommendations,
        meta={
            'total_scenarios_detected': len(ranked),
            'generated_at': window.date_to.isoformat(),
            'engine_version': 'phase2-controlled-scope',
            'tier': tier,
        },
    )

    if db is not None:
        _apply_digital_twin_optimizer(output=output, db=db, campaign_id=campaign_id)

    output.strategic_scores = compute_strategic_scores(output)
    output.executive_summary = build_executive_summary(output)
    return output


def _apply_digital_twin_optimizer(*, output: CampaignStrategyOut, db: Session, campaign_id: str) -> None:
    if not output.recommendations:
        output.meta['digital_twin'] = {
            'enabled': True,
            'status': 'no_recommendations',
            'winner_scenario_id': None,
        }
        return

    try:
        twin_state = DigitalTwinState.from_campaign_data(db, campaign_id)
        candidate_strategies: list[dict[str, Any]] = []

        for recommendation in output.recommendations:
            candidate_strategies.append(
                {
                    'strategy_id': recommendation.scenario_id,
                    'scenario_id': recommendation.scenario_id,
                    'strategy_actions': _recommendation_to_strategy_actions(recommendation.recommended_actions),
                }
            )

        winning = optimize_strategy(twin_state, candidate_strategies, db=db)
        if winning is None:
            output.meta['digital_twin'] = {
                'enabled': True,
                'status': 'no_candidates',
                'winner_scenario_id': None,
            }
            return

        output.meta['digital_twin'] = {
            'enabled': True,
            'status': 'optimized',
            'winner_scenario_id': str(winning['strategy_id']),
            'expected_value': float(winning['expected_value']),
            'simulation': dict(winning['simulation']),
        }
        output.meta['execution_candidate_scenarios'] = [str(winning['strategy_id'])]
    except Exception as exc:  # pragma: no cover
        output.meta['digital_twin'] = {
            'enabled': True,
            'status': 'failed',
            'error': str(exc),
            'winner_scenario_id': None,
        }


def _recommendation_to_strategy_actions(recommended_actions: list[str]) -> list[dict[str, int | str]]:
    actions: list[dict[str, int | str]] = []

    for action_text in recommended_actions:
        normalized = action_text.strip().lower()
        if 'link' in normalized:
            actions.append({'type': 'internal_link', 'count': 1})
        elif 'content' in normalized or 'publish' in normalized or 'refresh' in normalized:
            actions.append({'type': 'publish_content', 'pages': 1})
        elif 'title' in normalized or 'schema' in normalized or 'fix' in normalized or 'vital' in normalized:
            actions.append({'type': 'fix_technical_issues', 'count': 1})

    if not actions:
        actions.append({'type': 'publish_content', 'pages': 1})

    return actions


def _scenario_feature_name(scenario_id: str, scenario_category: str) -> str:
    if scenario_id in {'ranking_decline_detected', 'rank_negative_momentum', 'competitive_position_gap', 'competitive_momentum_gap'}:
        return 'ranking_velocity'
    if scenario_id in {'content_velocity_decline'}:
        return 'content_velocity'
    if scenario_id in {'core_web_vitals_failure'}:
        return 'technical_issue_density'
    if scenario_category == 'technical':
        return 'technical_issue_density'
    if scenario_category == 'organic':
        return 'ranking_velocity'
    return 'ranking_velocity'


def _cohort_pattern_multiplier_by_feature(db: Session, campaign_id: str) -> dict[str, float]:
    cohort_definition = describe_campaign_cohort(db, campaign_id)['cohort']
    rows = (
        db.query(StrategyCohortPattern)
        .filter(
            StrategyCohortPattern.cohort_definition == cohort_definition,
            StrategyCohortPattern.support_count >= 3,
            StrategyCohortPattern.confidence >= 0.6,
        )
        .order_by(StrategyCohortPattern.created_at.desc(), StrategyCohortPattern.id.desc())
        .all()
    )

    multipliers: dict[str, float] = {}
    for row in rows:
        feature_name = str(row.feature_name)
        influence = max(0.0, min(0.5, float(row.pattern_strength) * float(row.confidence) * 0.5))
        current = float(multipliers.get(feature_name, 1.0))
        multipliers[feature_name] = round(min(1.5, current + influence), 6)

    return multipliers


def _strategy_memory_multiplier_by_feature(db: Session, campaign_id: str) -> dict[str, float]:
    _ = campaign_id
    rows = (
        db.query(StrategyMemoryPattern)
        .filter(
            StrategyMemoryPattern.support_count >= 10,
            StrategyMemoryPattern.confidence_score >= 0.70,
        )
        .order_by(StrategyMemoryPattern.updated_at.desc(), StrategyMemoryPattern.id.desc())
        .all()
    )

    multipliers: dict[str, float] = {}
    for row in rows:
        feature_name = str(row.feature_name)
        confidence = max(0.0, min(1.0, float(row.confidence_score)))
        current = float(multipliers.get(feature_name, 1.0))
        multipliers[feature_name] = round(max(0.1, min(1.0, current * confidence)), 6)

    return multipliers

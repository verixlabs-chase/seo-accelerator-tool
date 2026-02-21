from __future__ import annotations

from app.services.strategy_engine.scenario_registry import SCENARIO_INDEX
from app.services.strategy_engine.schemas import CampaignStrategyOut, ExecutiveSummaryOut

_STRATEGIC_THEME_BY_DIMENSION: dict[str, str] = {
    "risk_index": "risk_containment",
    "opportunity_index": "growth_capture",
    "technical_health_score": "technical_stability",
    "local_authority_score": "local_authority_build",
    "competitive_pressure_score": "competitive_positioning",
    "strategy_score": "balanced_execution",
}

_FOCUS_BY_THEME: dict[str, str] = {
    "risk_containment": "stabilize_high_risk_scenarios",
    "growth_capture": "execute_high_opportunity_actions",
    "technical_stability": "improve_core_technical_reliability",
    "local_authority_build": "strengthen_local_reputation_and_presence",
    "competitive_positioning": "close_competitive_gaps",
    "balanced_execution": "maintain_balanced_program_execution",
}

_NEUTRAL = "neutral"


def _safe_category(scenario_id: str | None) -> str:
    if scenario_id is None:
        return _NEUTRAL
    scenario = SCENARIO_INDEX.get(scenario_id)
    if scenario is None:
        return _NEUTRAL
    return scenario.category


def build_executive_summary(strategy_output: CampaignStrategyOut) -> ExecutiveSummaryOut:
    scores = strategy_output.strategic_scores
    if scores is None:
        return ExecutiveSummaryOut(
            primary_issue_category=_NEUTRAL,
            top_priority_scenario=None,
            dominant_score_dimension="strategy_score",
            strategic_theme="balanced_execution",
            recommended_focus_area="maintain_balanced_program_execution",
            summary_confidence=0.5,
        )

    if not strategy_output.recommendations:
        return ExecutiveSummaryOut(
            primary_issue_category=_NEUTRAL,
            top_priority_scenario=None,
            dominant_score_dimension="strategy_score",
            strategic_theme="balanced_execution",
            recommended_focus_area="maintain_balanced_program_execution",
            summary_confidence=0.5,
        )

    top_recommendation = strategy_output.recommendations[0]
    top_scenario_id = top_recommendation.scenario_id
    primary_issue_category = _safe_category(top_scenario_id)

    dimension_values: dict[str, float] = {
        "risk_index": scores.risk_index,
        "opportunity_index": scores.opportunity_index,
        "technical_health_score": 100.0 - scores.technical_health_score,
        "local_authority_score": 100.0 - scores.local_authority_score,
        "competitive_pressure_score": scores.competitive_pressure_score if scores.competitive_pressure_score is not None else -1.0,
        "strategy_score": 100.0 - scores.strategy_score,
    }
    dominant_score_dimension = max(
        dimension_values,
        key=lambda key: (dimension_values[key], key),
    )
    strategic_theme = _STRATEGIC_THEME_BY_DIMENSION[dominant_score_dimension]
    recommended_focus_area = _FOCUS_BY_THEME[strategic_theme]

    # Summary confidence derives only from top recommendation confidence and concentration.
    concentration = 1.0 / len(strategy_output.recommendations)
    summary_confidence = max(0.0, min(1.0, (top_recommendation.confidence + (1.0 - concentration)) / 2.0))

    return ExecutiveSummaryOut(
        primary_issue_category=primary_issue_category,
        top_priority_scenario=top_scenario_id,
        dominant_score_dimension=dominant_score_dimension,
        strategic_theme=strategic_theme,
        recommended_focus_area=recommended_focus_area,
        summary_confidence=round(summary_confidence, 4),
    )


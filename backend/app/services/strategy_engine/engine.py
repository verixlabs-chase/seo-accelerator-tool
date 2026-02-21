from __future__ import annotations

from typing import Any

from app.services.strategy_engine.modules.competitor_diagnostics import run_competitor_diagnostics
from app.services.strategy_engine.modules.core_web_vitals_diagnostics import run_core_web_vitals_diagnostics
from app.services.strategy_engine.modules.ctr_diagnostics import run_ctr_diagnostics
from app.services.strategy_engine.modules.gbp_diagnostics import run_gbp_diagnostics
from app.services.strategy_engine.modules.ranking_diagnostics import run_ranking_diagnostics
from app.services.strategy_engine.executive_summary import build_executive_summary
from app.services.strategy_engine.priority_engine import PriorityInput, rank_priorities
from app.services.strategy_engine.scenario_registry import SCENARIO_INDEX
from app.services.strategy_engine.schemas import CampaignStrategyOut, DiagnosticResult, StrategyRecommendationOut, StrategyWindow
from app.services.strategy_engine.signal_models import build_signal_model
from app.services.strategy_engine.strategic_scoring import compute_strategic_scores


def build_campaign_strategy(
    campaign_id: str,
    window: StrategyWindow,
    raw_signals: dict[str, Any],
    tier: str,
) -> CampaignStrategyOut:
    """Deterministic strategy orchestration for the phase-2 controlled scope."""
    signals = build_signal_model(raw_signals)
    window_reference = f"{window.date_from.isoformat()}__{window.date_to.isoformat()}"

    diagnostics: list[DiagnosticResult] = []
    diagnostics.extend(run_ctr_diagnostics(signals, window_reference=window_reference, tier=tier))
    diagnostics.extend(run_core_web_vitals_diagnostics(signals, window_reference=window_reference))
    diagnostics.extend(run_ranking_diagnostics(signals, window_reference=window_reference))
    diagnostics.extend(run_gbp_diagnostics(signals, window_reference=window_reference, tier=tier))

    if tier == "enterprise":
        diagnostics.extend(run_competitor_diagnostics(signals, window_reference=window_reference))

    priority_inputs: list[PriorityInput] = []
    filtered_results: list[DiagnosticResult] = []
    for result in diagnostics:
        scenario = SCENARIO_INDEX.get(result.scenario_id)
        if scenario is None or scenario.deprecated:
            continue
        filtered_results.append(result)
        priority_inputs.append(
            PriorityInput(
                scenario_id=result.scenario_id,
                impact_weight=scenario.impact_weight,
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
            "total_scenarios_detected": len(ranked),
            "generated_at": window.date_to.isoformat(),
            "engine_version": "phase2-controlled-scope",
            "tier": tier,
        },
    )
    output.strategic_scores = compute_strategic_scores(output)
    output.executive_summary = build_executive_summary(output)
    return output

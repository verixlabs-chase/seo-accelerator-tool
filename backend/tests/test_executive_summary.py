from __future__ import annotations

from datetime import datetime, timezone

from app.services.strategy_engine.executive_summary import build_executive_summary
from app.services.strategy_engine.schemas import (
    CampaignStrategyOut,
    StrategicScoreOut,
    StrategyRecommendationOut,
    StrategyWindow,
)


def _window() -> StrategyWindow:
    return StrategyWindow(
        date_from=datetime(2026, 2, 1, tzinfo=timezone.utc),
        date_to=datetime(2026, 2, 20, tzinfo=timezone.utc),
    )


def _rec(scenario_id: str, priority_score: float, confidence: float, impact_level: str) -> StrategyRecommendationOut:
    return StrategyRecommendationOut(
        scenario_id=scenario_id,
        priority_score=priority_score,
        diagnosis="d",
        root_cause="r",
        recommended_actions=["a"],
        expected_outcome="o",
        authoritative_sources=["s"],
        confidence=confidence,
        impact_level=impact_level,
        evidence=[],
    )


def _output(scores: StrategicScoreOut, recommendations: list[StrategyRecommendationOut]) -> CampaignStrategyOut:
    return CampaignStrategyOut(
        campaign_id="camp-1",
        window=_window(),
        detected_scenarios=[item.scenario_id for item in recommendations],
        recommendations=recommendations,
        strategic_scores=scores,
        meta={"tier": "enterprise"},
    )


def test_executive_summary_deterministic_output() -> None:
    output = _output(
        StrategicScoreOut(
            strategy_score=60,
            technical_health_score=80,
            competitive_pressure_score=20,
            local_authority_score=70,
            risk_index=40,
            opportunity_index=30,
        ),
        [_rec("core_web_vitals_failure", 0.7, 0.8, "high")],
    )
    first = build_executive_summary(output)
    second = build_executive_summary(output)
    assert first.model_dump() == second.model_dump()


def test_executive_summary_high_risk_case() -> None:
    output = _output(
        StrategicScoreOut(
            strategy_score=30,
            technical_health_score=45,
            competitive_pressure_score=25,
            local_authority_score=55,
            risk_index=85,
            opportunity_index=20,
        ),
        [_rec("core_web_vitals_failure", 0.9, 0.95, "high")],
    )
    summary = build_executive_summary(output)
    assert summary.dominant_score_dimension == "risk_index"
    assert summary.strategic_theme == "risk_containment"


def test_executive_summary_competitive_pressure_dominant_case() -> None:
    output = _output(
        StrategicScoreOut(
            strategy_score=50,
            technical_health_score=88,
            competitive_pressure_score=92,
            local_authority_score=90,
            risk_index=20,
            opportunity_index=25,
        ),
        [_rec("competitor_reputation_gap", 0.8, 0.8, "medium")],
    )
    summary = build_executive_summary(output)
    assert summary.dominant_score_dimension == "competitive_pressure_score"
    assert summary.strategic_theme == "competitive_positioning"


def test_executive_summary_zero_scenario_neutral_case() -> None:
    output = _output(
        StrategicScoreOut(
            strategy_score=50,
            technical_health_score=50,
            competitive_pressure_score=None,
            local_authority_score=50,
            risk_index=50,
            opportunity_index=50,
        ),
        [],
    )
    summary = build_executive_summary(output)
    assert summary.primary_issue_category == "neutral"
    assert summary.top_priority_scenario is None
    assert summary.summary_confidence == 0.5


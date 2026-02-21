from __future__ import annotations

from datetime import datetime, timezone

from app.services.strategy_engine.schemas import CampaignStrategyOut, StrategyRecommendationOut, StrategyWindow
from app.services.strategy_engine.strategic_scoring import compute_strategic_scores


def _window() -> StrategyWindow:
    return StrategyWindow(
        date_from=datetime(2026, 2, 1, tzinfo=timezone.utc),
        date_to=datetime(2026, 2, 20, tzinfo=timezone.utc),
    )


def _base_output(*, tier: str, recommendations: list[StrategyRecommendationOut]) -> CampaignStrategyOut:
    return CampaignStrategyOut(
        campaign_id="camp-1",
        window=_window(),
        detected_scenarios=[item.scenario_id for item in recommendations],
        recommendations=recommendations,
        meta={"tier": tier},
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


def test_strategic_scoring_is_deterministic() -> None:
    output = _base_output(
        tier="enterprise",
        recommendations=[
            _rec("core_web_vitals_failure", 0.6, 0.8, "high"),
            _rec("competitor_reputation_gap", 0.4, 0.7, "medium"),
        ],
    )
    first = compute_strategic_scores(output)
    second = compute_strategic_scores(output)
    assert first.model_dump() == second.model_dump()


def test_strategic_scoring_clamps_scores() -> None:
    output = _base_output(
        tier="enterprise",
        recommendations=[
            _rec("core_web_vitals_failure", 10.0, 2.0, "high"),
            _rec("competitor_reputation_gap", 5.0, 1.5, "medium"),
        ],
    )
    scores = compute_strategic_scores(output)
    for value in [
        scores.strategy_score,
        scores.technical_health_score,
        scores.local_authority_score,
        scores.risk_index,
        scores.opportunity_index,
    ]:
        assert 0 <= value <= 100
    assert scores.competitive_pressure_score is not None
    assert 0 <= scores.competitive_pressure_score <= 100


def test_strategic_scoring_enterprise_vs_non_enterprise_competitive_score() -> None:
    recs = [_rec("competitor_reputation_gap", 0.5, 0.7, "medium")]
    enterprise = compute_strategic_scores(_base_output(tier="enterprise", recommendations=recs))
    non_enterprise = compute_strategic_scores(_base_output(tier="pro", recommendations=recs))
    assert enterprise.competitive_pressure_score is not None
    assert non_enterprise.competitive_pressure_score is None


def test_strategic_scoring_zero_scenario_case_neutral_baseline() -> None:
    scores = compute_strategic_scores(_base_output(tier="pro", recommendations=[]))
    assert scores.strategy_score == 50
    assert scores.technical_health_score == 50
    assert scores.local_authority_score == 50
    assert scores.risk_index == 50
    assert scores.opportunity_index == 50
    assert scores.competitive_pressure_score is None


def test_strategic_scoring_high_risk_scenario_increases_risk_index() -> None:
    low = compute_strategic_scores(
        _base_output(
            tier="enterprise",
            recommendations=[_rec("core_web_vitals_failure", 0.2, 0.6, "low")],
        )
    )
    high = compute_strategic_scores(
        _base_output(
            tier="enterprise",
            recommendations=[_rec("core_web_vitals_failure", 0.9, 0.95, "high")],
        )
    )
    assert high.risk_index > low.risk_index


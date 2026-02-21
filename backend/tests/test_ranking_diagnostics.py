from __future__ import annotations

from app.services.strategy_engine.modules import ranking_diagnostics
from app.services.strategy_engine.signal_models import StrategyEngineSignals


def _assert_evidence_shape(result) -> None:  # noqa: ANN001
    for evidence in result.evidence:
        payload = evidence.model_dump()
        assert set(payload.keys()) == {
            "signal_name",
            "signal_value",
            "threshold_reference",
            "comparator",
            "comparative_value",
            "window_reference",
        }


def test_ranking_positive_trigger() -> None:
    signals = StrategyEngineSignals(position_delta=3.0, traffic_growth_percent=-0.1)
    results = ranking_diagnostics.run_ranking_diagnostics(signals, "w")
    assert len(results) == 1
    assert results[0].scenario_id == "ranking_decline_detected"


def test_ranking_negative_non_trigger() -> None:
    signals = StrategyEngineSignals(position_delta=1.0, traffic_growth_percent=-0.01)
    results = ranking_diagnostics.run_ranking_diagnostics(signals, "w")
    assert results == []


def test_ranking_evidence_schema() -> None:
    signals = StrategyEngineSignals(position_delta=7.0)
    results = ranking_diagnostics.run_ranking_diagnostics(signals, "w")
    assert results
    _assert_evidence_shape(results[0])


def test_ranking_threshold_usage(monkeypatch) -> None:
    monkeypatch.setattr(ranking_diagnostics.thresholds, "RANKING_POSITION_DROP_THRESHOLD", 5.0)
    signals = StrategyEngineSignals(position_delta=3.0, traffic_growth_percent=-0.1)
    results = ranking_diagnostics.run_ranking_diagnostics(signals, "w")
    assert results == []


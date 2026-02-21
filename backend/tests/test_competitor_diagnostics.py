from __future__ import annotations

from app.services.strategy_engine.modules import competitor_diagnostics
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


def test_competitor_positive_trigger() -> None:
    signals = StrategyEngineSignals()
    results = competitor_diagnostics.run_competitor_diagnostics(signals, "w")
    assert len(results) == 1
    assert results[0].scenario_id == "competitor_data_unavailable"


def test_competitor_negative_non_trigger() -> None:
    signals = StrategyEngineSignals(
        avg_position=5.0,
        competitor_avg_position=5.0,
        avg_rating=4.5,
        competitor_rating=4.6,
    )
    results = competitor_diagnostics.run_competitor_diagnostics(signals, "w")
    assert results == []


def test_competitor_evidence_schema() -> None:
    signals = StrategyEngineSignals()
    results = competitor_diagnostics.run_competitor_diagnostics(signals, "w")
    assert results
    _assert_evidence_shape(results[0])


def test_competitor_threshold_usage(monkeypatch) -> None:
    monkeypatch.setattr(competitor_diagnostics.thresholds, "COMPETITOR_REQUIRED_SIGNAL_MIN_COUNT", 1)
    signals = StrategyEngineSignals(competitor_avg_position=5.0)
    results = competitor_diagnostics.run_competitor_diagnostics(signals, "w")
    assert results == []


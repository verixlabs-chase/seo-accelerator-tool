from __future__ import annotations

from app.services.strategy_engine.modules import ctr_diagnostics
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


def test_ctr_positive_trigger() -> None:
    signals = StrategyEngineSignals(impressions=1500, avg_position=4.0, ctr=0.01)
    results = ctr_diagnostics.run_ctr_diagnostics(signals, "w", tier="pro")
    assert any(item.scenario_id == "high_visibility_low_ctr" for item in results)


def test_ctr_negative_non_trigger() -> None:
    signals = StrategyEngineSignals(impressions=1500, avg_position=4.0, ctr=0.2)
    results = ctr_diagnostics.run_ctr_diagnostics(signals, "w", tier="pro")
    assert results == []


def test_ctr_evidence_schema() -> None:
    signals = StrategyEngineSignals(impressions=1500, avg_position=4.0, ctr=0.01)
    results = ctr_diagnostics.run_ctr_diagnostics(signals, "w", tier="pro")
    assert results
    _assert_evidence_shape(results[0])


def test_ctr_threshold_usage(monkeypatch) -> None:
    monkeypatch.setattr(ctr_diagnostics.thresholds, "HIGH_IMPRESSIONS_THRESHOLD", 5000)
    signals = StrategyEngineSignals(impressions=1500, avg_position=4.0, ctr=0.01)
    results = ctr_diagnostics.run_ctr_diagnostics(signals, "w", tier="pro")
    assert not any(item.scenario_id == "high_visibility_low_ctr" for item in results)


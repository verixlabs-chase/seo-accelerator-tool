from __future__ import annotations

from app.services.strategy_engine.modules import core_web_vitals_diagnostics
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


def test_core_web_vitals_positive_trigger() -> None:
    signals = StrategyEngineSignals(lcp=3.0)
    results = core_web_vitals_diagnostics.run_core_web_vitals_diagnostics(signals, "w")
    assert len(results) == 1
    assert results[0].scenario_id == "core_web_vitals_failure"


def test_core_web_vitals_negative_non_trigger() -> None:
    signals = StrategyEngineSignals(lcp=2.0, cls=0.05, inp=100, ttfb=200)
    results = core_web_vitals_diagnostics.run_core_web_vitals_diagnostics(signals, "w")
    assert results == []


def test_core_web_vitals_evidence_schema() -> None:
    signals = StrategyEngineSignals(lcp=3.0, cls=0.2)
    results = core_web_vitals_diagnostics.run_core_web_vitals_diagnostics(signals, "w")
    assert results
    _assert_evidence_shape(results[0])


def test_core_web_vitals_threshold_usage(monkeypatch) -> None:
    monkeypatch.setattr(core_web_vitals_diagnostics.thresholds, "LCP_THRESHOLD_SECONDS", 4.0)
    signals = StrategyEngineSignals(lcp=3.0)
    results = core_web_vitals_diagnostics.run_core_web_vitals_diagnostics(signals, "w")
    assert results == []


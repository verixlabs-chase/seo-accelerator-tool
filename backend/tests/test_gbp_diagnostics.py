from __future__ import annotations

from app.services.strategy_engine.modules import gbp_diagnostics
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


def test_gbp_positive_trigger() -> None:
    signals = StrategyEngineSignals(review_velocity=1.0, review_response_rate=0.5)
    results = gbp_diagnostics.run_gbp_diagnostics(signals, "w", tier="pro")
    ids = {item.scenario_id for item in results}
    assert "gbp_low_review_velocity" in ids
    assert "gbp_low_review_response_rate" in ids


def test_gbp_negative_non_trigger() -> None:
    signals = StrategyEngineSignals(review_velocity=4.0, review_response_rate=0.9)
    results = gbp_diagnostics.run_gbp_diagnostics(signals, "w", tier="pro")
    assert results == []


def test_gbp_evidence_schema() -> None:
    signals = StrategyEngineSignals(review_velocity=1.0)
    results = gbp_diagnostics.run_gbp_diagnostics(signals, "w", tier="pro")
    assert results
    _assert_evidence_shape(results[0])


def test_gbp_threshold_usage(monkeypatch) -> None:
    monkeypatch.setattr(gbp_diagnostics.thresholds, "GBP_REVIEW_VELOCITY_THRESHOLD", 0.5)
    signals = StrategyEngineSignals(review_velocity=1.0)
    results = gbp_diagnostics.run_gbp_diagnostics(signals, "w", tier="pro")
    assert not any(item.scenario_id == "gbp_low_review_velocity" for item in results)


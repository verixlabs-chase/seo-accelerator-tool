from __future__ import annotations

from app.services.strategy_engine import thresholds
from app.services.strategy_engine.schemas import DiagnosticResult, Evidence
from app.services.strategy_engine.signal_models import StrategyEngineSignals


def run_gbp_diagnostics(signals: StrategyEngineSignals, window_reference: str, tier: str) -> list[DiagnosticResult]:
    results: list[DiagnosticResult] = []

    if signals.review_velocity is not None and signals.review_velocity < thresholds.GBP_REVIEW_VELOCITY_THRESHOLD:
        evidence = [
            Evidence(
                signal_name="review_velocity",
                signal_value=signals.review_velocity,
                threshold_reference="GBP_REVIEW_VELOCITY_THRESHOLD",
                comparator="<",
                comparative_value=thresholds.GBP_REVIEW_VELOCITY_THRESHOLD,
                window_reference=window_reference,
            )
        ]
        results.append(
            DiagnosticResult(
                scenario_id="gbp_low_review_velocity",
                confidence=thresholds.DIAGNOSTIC_CONFIDENCE_MEDIUM,
                signal_magnitude=thresholds.MEDIUM_PRIORITY_SIGNAL_MAGNITUDE,
                evidence=evidence,
            )
        )

    if (
        signals.review_response_rate is not None
        and signals.review_response_rate < thresholds.GBP_REVIEW_RESPONSE_RATE_THRESHOLD
    ):
        evidence = [
            Evidence(
                signal_name="review_response_rate",
                signal_value=signals.review_response_rate,
                threshold_reference="GBP_REVIEW_RESPONSE_RATE_THRESHOLD",
                comparator="<",
                comparative_value=thresholds.GBP_REVIEW_RESPONSE_RATE_THRESHOLD,
                window_reference=window_reference,
            )
        ]
        results.append(
            DiagnosticResult(
                scenario_id="gbp_low_review_response_rate",
                confidence=thresholds.DIAGNOSTIC_CONFIDENCE_MEDIUM,
                signal_magnitude=thresholds.MEDIUM_PRIORITY_SIGNAL_MAGNITUDE,
                evidence=evidence,
            )
        )

    if tier != "enterprise":
        return results
    if signals.review_count is None or signals.competitor_review_count is None:
        return results

    competitor_gap = signals.competitor_review_count - signals.review_count
    if competitor_gap >= thresholds.GBP_COMPETITOR_REVIEW_COUNT_GAP_THRESHOLD:
        evidence = [
            Evidence(
                signal_name="review_count",
                signal_value=signals.review_count,
                threshold_reference="GBP_COMPETITOR_REVIEW_COUNT_GAP_THRESHOLD",
                comparator="<",
                comparative_value=signals.competitor_review_count,
                window_reference=window_reference,
            ),
            Evidence(
                signal_name="competitor_review_count",
                signal_value=signals.competitor_review_count,
                threshold_reference="GBP_COMPETITOR_REVIEW_COUNT_GAP_THRESHOLD",
                comparator="-",
                comparative_value=thresholds.GBP_COMPETITOR_REVIEW_COUNT_GAP_THRESHOLD,
                window_reference=window_reference,
            ),
        ]
        results.append(
            DiagnosticResult(
                scenario_id="low_review_velocity_vs_competitors",
                confidence=thresholds.DIAGNOSTIC_CONFIDENCE_MEDIUM,
                signal_magnitude=thresholds.MEDIUM_PRIORITY_SIGNAL_MAGNITUDE,
                evidence=evidence,
            )
        )
    return results


from __future__ import annotations

from app.services.strategy_engine import thresholds
from app.services.strategy_engine.schemas import DiagnosticResult, Evidence
from app.services.strategy_engine.signal_models import StrategyEngineSignals


def run_ctr_diagnostics(signals: StrategyEngineSignals, window_reference: str, tier: str) -> list[DiagnosticResult]:
    results: list[DiagnosticResult] = []
    if signals.impressions is None or signals.avg_position is None or signals.ctr is None:
        return results

    high_impressions = signals.impressions >= thresholds.HIGH_IMPRESSIONS_THRESHOLD
    in_position_band = (
        signals.avg_position >= thresholds.CTR_POSITION_MIN_THRESHOLD
        and signals.avg_position <= thresholds.CTR_POSITION_MAX_THRESHOLD
    )
    low_ctr = signals.ctr <= thresholds.CTR_LOW_THRESHOLD
    if high_impressions and in_position_band and low_ctr:
        evidence = [
            Evidence(
                signal_name="impressions",
                signal_value=signals.impressions,
                threshold_reference="HIGH_IMPRESSIONS_THRESHOLD",
                comparator=">=",
                comparative_value=thresholds.HIGH_IMPRESSIONS_THRESHOLD,
                window_reference=window_reference,
            ),
            Evidence(
                signal_name="avg_position",
                signal_value=signals.avg_position,
                threshold_reference="CTR_POSITION_MIN_THRESHOLD/CTR_POSITION_MAX_THRESHOLD",
                comparator="between",
                comparative_value=signals.avg_position,
                window_reference=window_reference,
            ),
            Evidence(
                signal_name="ctr",
                signal_value=signals.ctr,
                threshold_reference="CTR_LOW_THRESHOLD",
                comparator="<=",
                comparative_value=thresholds.CTR_LOW_THRESHOLD,
                window_reference=window_reference,
            ),
        ]
        results.append(
            DiagnosticResult(
                scenario_id="high_visibility_low_ctr",
                confidence=thresholds.DIAGNOSTIC_CONFIDENCE_HIGH,
                signal_magnitude=thresholds.HIGH_PRIORITY_SIGNAL_MAGNITUDE,
                evidence=evidence,
            )
        )

    if tier != "enterprise":
        return results

    if signals.competitor_ctr_estimate is None:
        return results
    if signals.ctr is None:
        return results

    competitor_gap = signals.competitor_ctr_estimate - signals.ctr
    if competitor_gap >= thresholds.CTR_COMPETITOR_GAP_THRESHOLD:
        evidence = [
            Evidence(
                signal_name="ctr",
                signal_value=signals.ctr,
                threshold_reference="CTR_COMPETITOR_GAP_THRESHOLD",
                comparator="<",
                comparative_value=signals.competitor_ctr_estimate,
                window_reference=window_reference,
            ),
            Evidence(
                signal_name="competitor_ctr_estimate",
                signal_value=signals.competitor_ctr_estimate,
                threshold_reference="CTR_COMPETITOR_GAP_THRESHOLD",
                comparator="-",
                comparative_value=thresholds.CTR_COMPETITOR_GAP_THRESHOLD,
                window_reference=window_reference,
            ),
        ]
        results.append(
            DiagnosticResult(
                scenario_id="competitive_snippet_disadvantage",
                confidence=thresholds.DIAGNOSTIC_CONFIDENCE_MEDIUM,
                signal_magnitude=thresholds.MEDIUM_PRIORITY_SIGNAL_MAGNITUDE,
                evidence=evidence,
            )
        )
    return results


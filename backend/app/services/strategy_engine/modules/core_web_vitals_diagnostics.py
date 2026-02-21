from __future__ import annotations

from app.services.strategy_engine import thresholds
from app.services.strategy_engine.schemas import DiagnosticResult, Evidence
from app.services.strategy_engine.signal_models import StrategyEngineSignals


def _bounded_ratio(value: float, threshold_value: float) -> float:
    if threshold_value <= 0:
        return 0.0
    return min(value / threshold_value, thresholds.CWV_SEVERITY_CAP)


def run_core_web_vitals_diagnostics(signals: StrategyEngineSignals, window_reference: str) -> list[DiagnosticResult]:
    failures: list[Evidence] = []
    weighted_severity = 0.0

    if signals.lcp is not None and signals.lcp > thresholds.LCP_THRESHOLD_SECONDS:
        weighted_severity += _bounded_ratio(signals.lcp, thresholds.LCP_THRESHOLD_SECONDS) * thresholds.CWV_LCP_WEIGHT
        failures.append(
            Evidence(
                signal_name="lcp",
                signal_value=signals.lcp,
                threshold_reference="LCP_THRESHOLD_SECONDS",
                comparator=">",
                comparative_value=thresholds.LCP_THRESHOLD_SECONDS,
                window_reference=window_reference,
            )
        )
    if signals.cls is not None and signals.cls > thresholds.CLS_THRESHOLD:
        weighted_severity += _bounded_ratio(signals.cls, thresholds.CLS_THRESHOLD) * thresholds.CWV_CLS_WEIGHT
        failures.append(
            Evidence(
                signal_name="cls",
                signal_value=signals.cls,
                threshold_reference="CLS_THRESHOLD",
                comparator=">",
                comparative_value=thresholds.CLS_THRESHOLD,
                window_reference=window_reference,
            )
        )
    if signals.inp is not None and signals.inp > thresholds.INP_THRESHOLD_MS:
        weighted_severity += _bounded_ratio(signals.inp, thresholds.INP_THRESHOLD_MS) * thresholds.CWV_INP_WEIGHT
        failures.append(
            Evidence(
                signal_name="inp",
                signal_value=signals.inp,
                threshold_reference="INP_THRESHOLD_MS",
                comparator=">",
                comparative_value=thresholds.INP_THRESHOLD_MS,
                window_reference=window_reference,
            )
        )
    if signals.ttfb is not None and signals.ttfb > thresholds.TTFB_THRESHOLD_MS:
        weighted_severity += _bounded_ratio(signals.ttfb, thresholds.TTFB_THRESHOLD_MS) * thresholds.CWV_TTFB_WEIGHT
        failures.append(
            Evidence(
                signal_name="ttfb",
                signal_value=signals.ttfb,
                threshold_reference="TTFB_THRESHOLD_MS",
                comparator=">",
                comparative_value=thresholds.TTFB_THRESHOLD_MS,
                window_reference=window_reference,
            )
        )

    if not failures:
        return []

    severity_magnitude = min(weighted_severity / thresholds.CWV_SEVERITY_CAP, 1.0)
    confidence = min(
        thresholds.CWV_BASE_CONFIDENCE + (severity_magnitude * thresholds.CWV_CONFIDENCE_MULTIPLIER),
        1.0,
    )
    return [
        DiagnosticResult(
            scenario_id="core_web_vitals_failure",
            confidence=confidence,
            signal_magnitude=severity_magnitude,
            evidence=failures,
        )
    ]


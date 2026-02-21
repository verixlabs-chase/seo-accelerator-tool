from __future__ import annotations

from app.services.strategy_engine import thresholds
from app.services.strategy_engine.schemas import DiagnosticResult, Evidence
from app.services.strategy_engine.signal_models import StrategyEngineSignals


def run_ranking_diagnostics(signals: StrategyEngineSignals, window_reference: str) -> list[DiagnosticResult]:
    if signals.position_delta is None:
        return []

    severe_position_drop = signals.position_delta >= thresholds.RANKING_SEVERE_POSITION_DROP_THRESHOLD
    severe_traffic_drop = (
        signals.traffic_growth_percent is not None
        and signals.traffic_growth_percent <= thresholds.RANKING_SEVERE_TRAFFIC_DECLINE_THRESHOLD
    )

    if severe_position_drop or severe_traffic_drop:
        evidence = [
            Evidence(
                signal_name="position_delta",
                signal_value=signals.position_delta,
                threshold_reference="RANKING_SEVERE_POSITION_DROP_THRESHOLD",
                comparator=">=",
                comparative_value=thresholds.RANKING_SEVERE_POSITION_DROP_THRESHOLD,
                window_reference=window_reference,
            )
        ]
        if signals.traffic_growth_percent is not None:
            evidence.append(
                Evidence(
                    signal_name="traffic_growth_percent",
                    signal_value=signals.traffic_growth_percent,
                    threshold_reference="RANKING_SEVERE_TRAFFIC_DECLINE_THRESHOLD",
                    comparator="<=",
                    comparative_value=thresholds.RANKING_SEVERE_TRAFFIC_DECLINE_THRESHOLD,
                    window_reference=window_reference,
                )
            )
        return [
            DiagnosticResult(
                scenario_id="ranking_decline_detected",
                confidence=thresholds.DIAGNOSTIC_CONFIDENCE_HIGH,
                signal_magnitude=thresholds.HIGH_PRIORITY_SIGNAL_MAGNITUDE,
                evidence=evidence,
            )
        ]

    # Cross-signal requirement for non-severe ranking decline.
    if signals.traffic_growth_percent is None:
        return []
    moderate_position_drop = signals.position_delta >= thresholds.RANKING_POSITION_DROP_THRESHOLD
    traffic_decline = signals.traffic_growth_percent <= thresholds.RANKING_TRAFFIC_DECLINE_THRESHOLD
    if not (moderate_position_drop and traffic_decline):
        return []

    evidence = [
        Evidence(
            signal_name="position_delta",
            signal_value=signals.position_delta,
            threshold_reference="RANKING_POSITION_DROP_THRESHOLD",
            comparator=">=",
            comparative_value=thresholds.RANKING_POSITION_DROP_THRESHOLD,
            window_reference=window_reference,
        ),
        Evidence(
            signal_name="traffic_growth_percent",
            signal_value=signals.traffic_growth_percent,
            threshold_reference="RANKING_TRAFFIC_DECLINE_THRESHOLD",
            comparator="<=",
            comparative_value=thresholds.RANKING_TRAFFIC_DECLINE_THRESHOLD,
            window_reference=window_reference,
        ),
    ]
    return [
        DiagnosticResult(
            scenario_id="ranking_decline_detected",
            confidence=thresholds.DIAGNOSTIC_CONFIDENCE_MEDIUM,
            signal_magnitude=thresholds.MEDIUM_PRIORITY_SIGNAL_MAGNITUDE,
            evidence=evidence,
        )
    ]


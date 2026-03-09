from __future__ import annotations

from app.services.strategy_engine import thresholds
from app.services.strategy_engine.schemas import DiagnosticResult, Evidence
from app.services.strategy_engine.signal_models import StrategyEngineSignals


def run_competitor_diagnostics(signals: StrategyEngineSignals, window_reference: str) -> list[DiagnosticResult]:
    results: list[DiagnosticResult] = []
    present_signal_count = 0

    competitor_signals: list[tuple[str, float | bool | None]] = [
        ("competitor_avg_position", signals.competitor_avg_position),
        ("competitor_ctr_estimate", signals.competitor_ctr_estimate),
        ("competitor_lcp", signals.competitor_lcp),
        ("competitor_word_count", signals.competitor_word_count),
        ("competitor_schema_presence", signals.competitor_schema_presence),
        ("competitor_review_count", signals.competitor_review_count),
        ("competitor_rating", signals.competitor_rating),
    ]
    for _name, value in competitor_signals:
        if value is not None:
            present_signal_count += 1

    if present_signal_count < thresholds.COMPETITOR_REQUIRED_SIGNAL_MIN_COUNT:
        results.append(
            DiagnosticResult(
                scenario_id="competitor_data_unavailable",
                confidence=thresholds.DIAGNOSTIC_CONFIDENCE_LOW,
                signal_magnitude=thresholds.LOW_PRIORITY_SIGNAL_MAGNITUDE,
                evidence=[
                    Evidence(
                        signal_name="competitor_signal_count",
                        signal_value=float(present_signal_count),
                        threshold_reference="COMPETITOR_REQUIRED_SIGNAL_MIN_COUNT",
                        comparator="<",
                        comparative_value=float(thresholds.COMPETITOR_REQUIRED_SIGNAL_MIN_COUNT),
                        window_reference=window_reference,
                    )
                ],
            )
        )
        return results

    if signals.avg_rating is not None and signals.competitor_rating is not None:
        rating_gap = signals.competitor_rating - signals.avg_rating
        if rating_gap >= thresholds.COMPETITOR_RATING_GAP_THRESHOLD:
            results.append(
                DiagnosticResult(
                    scenario_id="competitor_reputation_gap",
                    confidence=thresholds.DIAGNOSTIC_CONFIDENCE_MEDIUM,
                    signal_magnitude=thresholds.MEDIUM_PRIORITY_SIGNAL_MAGNITUDE,
                    evidence=[
                        Evidence(
                            signal_name="avg_rating",
                            signal_value=signals.avg_rating,
                            threshold_reference="COMPETITOR_RATING_GAP_THRESHOLD",
                            comparator="<",
                            comparative_value=signals.competitor_rating,
                            window_reference=window_reference,
                        )
                    ],
                )
            )

    if signals.avg_position is not None and signals.competitor_avg_position is not None:
        position_gap = signals.avg_position - signals.competitor_avg_position
        if position_gap >= thresholds.COMPETITOR_POSITION_GAP_THRESHOLD:
            results.append(
                DiagnosticResult(
                    scenario_id="competitive_position_gap",
                    confidence=thresholds.DIAGNOSTIC_CONFIDENCE_MEDIUM,
                    signal_magnitude=thresholds.MEDIUM_PRIORITY_SIGNAL_MAGNITUDE,
                    evidence=[
                        Evidence(
                            signal_name="avg_position",
                            signal_value=signals.avg_position,
                            threshold_reference="COMPETITOR_POSITION_GAP_THRESHOLD",
                            comparator=">",
                            comparative_value=signals.competitor_avg_position,
                            window_reference=window_reference,
                        )
                    ],
                )
            )
    return results


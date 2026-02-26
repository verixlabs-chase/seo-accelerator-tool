from __future__ import annotations

from app.services.strategy_engine.temporal_math import PRECISION

DELTA_SIMULATOR_VERSION = 'delta-simulator-v1'


def _bounded(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def simulate_recommendation_effect(
    baseline_metrics: dict[str, float],
    projected_delta: dict[str, float],
    confidence_range: tuple[float, float],
) -> dict[str, object]:
    baseline_rank = float(baseline_metrics.get('avg_rank_position', 0.0))
    baseline_traffic = float(baseline_metrics.get('organic_traffic', 0.0))
    baseline_conversions = float(baseline_metrics.get('conversions', 0.0))

    rank_shift = float(projected_delta.get('rank_shift', 0.0))
    traffic_delta_rate = float(projected_delta.get('traffic_delta_rate', 0.0))
    conversion_delta_rate = float(projected_delta.get('conversion_delta_rate', 0.0))

    confidence_low = _bounded(float(confidence_range[0]), 0.0, 1.0)
    confidence_high = _bounded(float(confidence_range[1]), 0.0, 1.0)
    if confidence_low > confidence_high:
        confidence_low, confidence_high = confidence_high, confidence_low

    projected_rank_shift = round(baseline_rank + rank_shift, PRECISION)
    projected_traffic_delta = round(baseline_traffic * traffic_delta_rate, PRECISION)
    projected_conversion_delta = round(baseline_conversions * conversion_delta_rate, PRECISION)

    risk_base = abs(rank_shift) * 0.2 + abs(traffic_delta_rate) * 25.0 + abs(conversion_delta_rate) * 35.0
    confidence_spread = max(0.0, confidence_high - confidence_low)
    risk_score = round(_bounded(risk_base + confidence_spread * 20.0, 0.0, 100.0), PRECISION)

    confidence_adjusted_range = {
        'traffic_delta': {
            'low': round(projected_traffic_delta * confidence_low, PRECISION),
            'high': round(projected_traffic_delta * confidence_high, PRECISION),
        },
        'conversion_delta': {
            'low': round(projected_conversion_delta * confidence_low, PRECISION),
            'high': round(projected_conversion_delta * confidence_high, PRECISION),
        },
    }

    return {
        'projected_rank_shift': projected_rank_shift,
        'projected_traffic_delta': projected_traffic_delta,
        'projected_conversion_delta': projected_conversion_delta,
        'risk_score': risk_score,
        'confidence_adjusted_range': confidence_adjusted_range,
        'simulator_version': DELTA_SIMULATOR_VERSION,
    }

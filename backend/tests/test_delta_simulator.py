from __future__ import annotations

from app.services.strategy_engine.delta_simulator import simulate_recommendation_effect


def test_delta_simulator_rule_based_projection() -> None:
    result = simulate_recommendation_effect(
        baseline_metrics={
            'avg_rank_position': 12.0,
            'organic_traffic': 1000.0,
            'conversions': 50.0,
        },
        projected_delta={
            'rank_shift': -1.5,
            'traffic_delta_rate': 0.12,
            'conversion_delta_rate': 0.08,
        },
        confidence_range=(0.6, 0.9),
    )

    assert result['projected_rank_shift'] == 10.5
    assert result['projected_traffic_delta'] == 120.0
    assert result['projected_conversion_delta'] == 4.0
    assert 0.0 <= result['risk_score'] <= 100.0
    assert result['confidence_adjusted_range']['traffic_delta']['low'] == 72.0
    assert result['confidence_adjusted_range']['traffic_delta']['high'] == 108.0


def test_delta_simulator_confidence_range_ordering() -> None:
    result = simulate_recommendation_effect(
        baseline_metrics={'avg_rank_position': 5.0, 'organic_traffic': 200.0, 'conversions': 20.0},
        projected_delta={'rank_shift': 0.2, 'traffic_delta_rate': -0.1, 'conversion_delta_rate': -0.2},
        confidence_range=(0.9, 0.4),
    )
    low = result['confidence_adjusted_range']['conversion_delta']['low']
    high = result['confidence_adjusted_range']['conversion_delta']['high']
    assert min(low, high) == -3.6
    assert max(low, high) == -1.6

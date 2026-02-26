from __future__ import annotations

from app.services.strategy_engine.competitive_trajectory import (
    classify_relative_momentum,
    compute_relative_momentum_score,
)


def test_relative_momentum_score_identical_slopes() -> None:
    assert compute_relative_momentum_score(0.2, 0.2, impact_weight=1.5) == 0.0


def test_classify_relative_momentum_flat_slope_stagnating() -> None:
    status = classify_relative_momentum(our_slope=0.0, competitor_slope=0.0, volatility=0.1)
    assert status == 'stagnating'


def test_classify_relative_momentum_gaining_ground() -> None:
    status = classify_relative_momentum(our_slope=0.2, competitor_slope=0.1, volatility=0.2)
    assert status == 'gaining_ground'


def test_classify_relative_momentum_losing_ground() -> None:
    status = classify_relative_momentum(our_slope=-0.2, competitor_slope=0.1, volatility=0.2)
    assert status == 'losing_ground'


def test_classify_relative_momentum_extreme_volatility() -> None:
    status = classify_relative_momentum(our_slope=0.5, competitor_slope=-0.5, volatility=1.0)
    assert status == 'volatile'

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.services.strategy_engine.temporal_math import (
    compute_acceleration,
    compute_decay_half_life,
    compute_slope,
    compute_trend_strength,
    compute_volatility,
)


def _timestamps() -> list[datetime]:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    return [start + timedelta(days=offset) for offset in range(5)]


def test_compute_slope_positive_line() -> None:
    slope = compute_slope([1, 2, 3, 4, 5], _timestamps())
    assert slope == 1.0


def test_compute_slope_stable_ordering_with_unsorted_timestamps() -> None:
    stamps = _timestamps()
    values = [5, 1, 4, 2, 3]
    shuffled = [stamps[4], stamps[0], stamps[3], stamps[1], stamps[2]]
    slope = compute_slope(values, shuffled)
    assert slope == 1.0


def test_compute_acceleration_detects_curve() -> None:
    acceleration = compute_acceleration([1, 2, 4, 7, 11], _timestamps())
    assert acceleration > 0.0


def test_compute_volatility_zero_for_flat_series() -> None:
    assert compute_volatility([2, 2, 2, 2]) == 0.0


def test_compute_decay_half_life_for_decay_series() -> None:
    half_life = compute_decay_half_life([100, 80, 64, 51.2, 40.96])
    assert half_life == pytest.approx(3.106284, rel=1e-6)


def test_compute_trend_strength_increases_with_signal_direction() -> None:
    weak = compute_trend_strength([5, 5.1, 5.0, 5.1, 5.0])
    strong = compute_trend_strength([1, 2, 3, 4, 5])
    assert strong > weak

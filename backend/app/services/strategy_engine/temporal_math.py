from __future__ import annotations

import hashlib
import math
from datetime import datetime

PRECISION = 6
TEMPORAL_MATH_VERSION = 'temporal-math-v1'
TEMPORAL_MATH_VERSION_HASH = hashlib.sha256(TEMPORAL_MATH_VERSION.encode('utf-8')).hexdigest()


def _round(value: float) -> float:
    return round(float(value), PRECISION)


def _sorted_pairs(values: list[float], timestamps: list[datetime]) -> tuple[list[float], list[datetime]]:
    if len(values) != len(timestamps):
        raise ValueError('values and timestamps must have identical lengths')
    if len(values) == 0:
        return [], []

    indexed = [(timestamps[idx], idx, float(values[idx])) for idx in range(len(values))]
    indexed.sort(key=lambda item: (item[0], item[1]))
    ordered_values = [item[2] for item in indexed]
    ordered_timestamps = [item[0] for item in indexed]
    return ordered_values, ordered_timestamps


def _time_axis_days(timestamps: list[datetime]) -> list[float]:
    if not timestamps:
        return []
    start = timestamps[0].timestamp()
    axis = [(stamp.timestamp() - start) / 86400.0 for stamp in timestamps]
    if all(math.isclose(point, 0.0, abs_tol=1e-12) for point in axis):
        return [float(idx) for idx in range(len(timestamps))]
    return axis


def _linear_slope(values: list[float], axis: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean_x = sum(axis) / len(axis)
    mean_y = sum(values) / len(values)
    denom = sum((x - mean_x) ** 2 for x in axis)
    if math.isclose(denom, 0.0, abs_tol=1e-12):
        return 0.0
    numer = sum((x - mean_x) * (y - mean_y) for x, y in zip(axis, values, strict=False))
    return numer / denom


def compute_slope(values: list[float], timestamps: list[datetime]) -> float:
    ordered_values, ordered_timestamps = _sorted_pairs(values, timestamps)
    if len(ordered_values) < 2:
        return 0.0
    axis = _time_axis_days(ordered_timestamps)
    return _round(_linear_slope(ordered_values, axis))


def compute_acceleration(values: list[float], timestamps: list[datetime]) -> float:
    ordered_values, ordered_timestamps = _sorted_pairs(values, timestamps)
    if len(ordered_values) < 3:
        return 0.0

    axis = _time_axis_days(ordered_timestamps)
    segment_slopes: list[float] = []
    segment_axis: list[float] = []
    for idx in range(1, len(ordered_values)):
        dt = axis[idx] - axis[idx - 1]
        if math.isclose(dt, 0.0, abs_tol=1e-12):
            continue
        segment_slopes.append((ordered_values[idx] - ordered_values[idx - 1]) / dt)
        segment_axis.append((axis[idx] + axis[idx - 1]) / 2.0)

    if len(segment_slopes) < 2:
        return 0.0
    return _round(_linear_slope(segment_slopes, segment_axis))


def compute_volatility(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    normalized = [float(item) for item in values]
    mean_value = sum(normalized) / len(normalized)
    variance = sum((item - mean_value) ** 2 for item in normalized) / len(normalized)
    return _round(math.sqrt(variance))


def compute_decay_half_life(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    start = float(values[0])
    end = float(values[-1])
    if start <= 0 or end <= 0 or end >= start:
        return 0.0

    elapsed = float(len(values) - 1)
    ratio = end / start
    if math.isclose(ratio, 1.0, abs_tol=1e-12) or ratio <= 0:
        return 0.0
    half_life = elapsed * math.log(0.5) / math.log(ratio)
    return _round(max(half_life, 0.0))


def compute_trend_strength(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    slope = abs(_linear_slope([float(v) for v in values], [float(idx) for idx in range(len(values))]))
    volatility = compute_volatility(values)
    if math.isclose(volatility, 0.0, abs_tol=1e-12):
        return _round(1.0 if slope > 0 else 0.0)
    return _round(min(1.0, slope / (volatility + 1e-9)))

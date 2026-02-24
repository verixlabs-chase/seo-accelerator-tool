from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

FloatPrecisionMap = dict[str, int]

_DEFAULT_FLOAT_PRECISION = 6
_DEFAULT_DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def quantize_float(value: float, precision: int = _DEFAULT_FLOAT_PRECISION) -> float:
    if precision < 0:
        raise ValueError("precision must be non-negative")
    quantizer = Decimal("1").scaleb(-precision)
    quantized = Decimal(str(value)).quantize(quantizer, rounding=ROUND_HALF_UP)
    return float(quantized)


def normalize_datetime(value: datetime) -> str:
    if value.tzinfo is None:
        normalized = value.replace(tzinfo=UTC)
    else:
        normalized = value.astimezone(UTC)
    return normalized.strftime(_DEFAULT_DATETIME_FORMAT)


def canonicalize_payload(payload: Any, *, float_precision: int = _DEFAULT_FLOAT_PRECISION) -> Any:
    return _canonicalize(payload, float_precision=float_precision)


def _canonicalize(value: Any, *, float_precision: int) -> Any:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return quantize_float(value, precision=float_precision)
    if isinstance(value, Decimal):
        return quantize_float(float(value), precision=float_precision)
    if isinstance(value, datetime):
        return normalize_datetime(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        # Lists are intentionally kept in stable input order; elements are canonicalized recursively.
        return [_canonicalize(item, float_precision=float_precision) for item in value]
    if isinstance(value, tuple):
        return [_canonicalize(item, float_precision=float_precision) for item in value]
    if isinstance(value, dict):
        return {
            str(key): _canonicalize(value[key], float_precision=float_precision)
            for key in sorted(value.keys(), key=lambda item: str(item))
        }
    if hasattr(value, "model_dump"):
        dumped = value.model_dump(mode="python")
        return _canonicalize(dumped, float_precision=float_precision)
    if hasattr(value, "dict"):
        dumped = value.dict()
        return _canonicalize(dumped, float_precision=float_precision)
    return str(value)

from __future__ import annotations

import json
from hashlib import sha256
from typing import Any

TRACE_PRECISION = 6


def _canonicalize(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, TRACE_PRECISION)
    if isinstance(value, dict):
        return {key: _canonicalize(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_canonicalize(item) for item in value]
    return value


def build_decision_trace(
    *,
    rule_evaluations: list[dict[str, Any]],
    threshold_values: dict[str, Any],
    momentum_inputs: dict[str, Any],
    volatility_inputs: dict[str, Any],
    allocation_weights: dict[str, Any],
    confidence_adjustments: list[dict[str, Any]],
) -> dict[str, Any]:
    trace = {
        'rule_evaluations': rule_evaluations,
        'threshold_values': threshold_values,
        'momentum_inputs': momentum_inputs,
        'volatility_inputs': volatility_inputs,
        'allocation_weights': allocation_weights,
        'confidence_adjustments': confidence_adjustments,
    }
    return _canonicalize(trace)


def serialize_trace_payload(payload: dict[str, Any]) -> str:
    return json.dumps(_canonicalize(payload), sort_keys=True, separators=(',', ':'))


def compute_trace_hash(trace_payload: dict[str, Any]) -> str:
    serialized = serialize_trace_payload(trace_payload)
    return sha256(serialized.encode('utf-8')).hexdigest()
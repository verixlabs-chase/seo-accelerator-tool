from __future__ import annotations

from hashlib import sha256
import json
from typing import Any

PRECISION = 6
ALLOCATION_VERSION = "v1"
DEFAULT_MAX_SHIFT = 0.2


def allocate_portfolio_capital(
    campaign_inputs: list[dict[str, Any]],
    *,
    max_shift: float = DEFAULT_MAX_SHIFT,
) -> dict[str, Any]:
    """Pure deterministic allocator with bounded per-campaign shift."""
    bounded_shift = max(0.0, min(float(max_shift), 1.0))
    ordered = sorted(campaign_inputs, key=lambda item: str(item["campaign_id"]))
    if not ordered:
        payload = {
            "version": ALLOCATION_VERSION,
            "max_shift": round(bounded_shift, PRECISION),
            "campaign_count": 0,
            "allocations": [],
            "allocation_sum": 0.0,
        }
        return _with_hash(payload)

    base = _normalize(
        [max(float(item.get("current_allocation", 0.0)), 0.0) for item in ordered],
        fallback_equal_share=True,
    )
    target = _normalize(
        [max(float(item.get("opportunity_score", 0.0)), 0.0) for item in ordered],
        fallback_equal_share=False,
    )
    if sum(target) <= 0.0:
        target = list(base)

    bounded: list[float] = []
    for base_weight, target_weight in zip(base, target):
        delta = target_weight - base_weight
        clamped_delta = max(-bounded_shift, min(bounded_shift, delta))
        bounded.append(max(0.0, base_weight + clamped_delta))

    normalized = _normalize(bounded, fallback_equal_share=True)
    rounded = [round(value, PRECISION) for value in normalized]
    remainder = round(1.0 - sum(rounded), PRECISION)
    rounded[-1] = round(rounded[-1] + remainder, PRECISION)

    allocations: list[dict[str, Any]] = []
    for item, base_weight, final_weight in zip(ordered, base, rounded):
        allocations.append(
            {
                "campaign_id": item["campaign_id"],
                "allocation": final_weight,
                "delta": round(final_weight - round(base_weight, PRECISION), PRECISION),
            }
        )

    payload = {
        "version": ALLOCATION_VERSION,
        "max_shift": round(bounded_shift, PRECISION),
        "campaign_count": len(ordered),
        "allocations": allocations,
        "allocation_sum": round(sum(weight["allocation"] for weight in allocations), PRECISION),
    }
    return _with_hash(payload)


def _normalize(values: list[float], *, fallback_equal_share: bool) -> list[float]:
    total = sum(values)
    if total > 0.0:
        return [value / total for value in values]
    if not fallback_equal_share or not values:
        return [0.0 for _ in values]
    equal_share = 1.0 / len(values)
    return [equal_share for _ in values]


def _with_hash(payload: dict[str, Any]) -> dict[str, Any]:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    with_hash = dict(payload)
    with_hash["hash"] = sha256(serialized.encode("utf-8")).hexdigest()
    return with_hash
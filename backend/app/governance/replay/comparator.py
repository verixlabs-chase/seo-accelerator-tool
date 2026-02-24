from __future__ import annotations

import difflib
import json
from typing import Any

from app.governance.replay.canonicalize import canonicalize_payload
from app.governance.replay.hashing import output_hash


def compare_hashes(expected_payload: Any, actual_payload: Any) -> tuple[bool, str, str]:
    expected = output_hash(expected_payload)
    actual = output_hash(actual_payload)
    return expected == actual, expected, actual


def compare_ordering(expected_payload: dict[str, Any], actual_payload: dict[str, Any], *, path: str = "recommendations") -> tuple[bool, list[str], list[str]]:
    expected_items = _extract_ordering(expected_payload, path)
    actual_items = _extract_ordering(actual_payload, path)
    return expected_items == actual_items, expected_items, actual_items


def compare_confidence_bands(expected_payload: dict[str, Any], actual_payload: dict[str, Any], *, path: str = "recommendations") -> tuple[bool, list[str], list[str]]:
    expected_bands = _extract_confidence_bands(expected_payload, path)
    actual_bands = _extract_confidence_bands(actual_payload, path)
    return expected_bands == actual_bands, expected_bands, actual_bands


def diff_payload(expected_payload: Any, actual_payload: Any) -> str:
    expected_text = json.dumps(canonicalize_payload(expected_payload), indent=2, sort_keys=True)
    actual_text = json.dumps(canonicalize_payload(actual_payload), indent=2, sort_keys=True)
    return "\n".join(
        difflib.unified_diff(
            expected_text.splitlines(),
            actual_text.splitlines(),
            fromfile="expected",
            tofile="actual",
            lineterm="",
        )
    )


def _extract_ordering(payload: dict[str, Any], path: str) -> list[str]:
    values = payload.get(path, [])
    if not isinstance(values, list):
        return []
    output: list[str] = []
    for item in values:
        if isinstance(item, dict):
            scenario_id = item.get("scenario_id")
            if isinstance(scenario_id, str):
                output.append(scenario_id)
    return output


def _extract_confidence_bands(payload: dict[str, Any], path: str) -> list[str]:
    values = payload.get(path, [])
    if not isinstance(values, list):
        return []
    bands: list[str] = []
    for item in values:
        confidence = item.get("confidence") if isinstance(item, dict) else None
        if isinstance(confidence, (float, int)):
            bands.append(_band(float(confidence)))
    return bands


def _band(value: float) -> str:
    if value >= 0.8:
        return "high"
    if value >= 0.6:
        return "medium"
    return "low"

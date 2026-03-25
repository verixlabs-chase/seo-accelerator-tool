from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any


_CLASSIFICATION_PRIORITY = {
    "provider_backed": 0,
    "generated": 1,
    "scheduled": 2,
    "in_progress": 1,
    "stale": 2,
    "minimal_artifact": 3,
    "operator_assisted": 3,
    "delivery_unverified": 4,
    "non_durable": 5,
    "heuristic": 4,
    "synthetic": 5,
    "unavailable": 6,
}


def build_truth(
    *,
    states: list[str],
    summary: str,
    provider_state: str,
    setup_state: str,
    operator_state: str,
    freshness_state: str = "unknown",
    reasons: list[str] | None = None,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    normalized_states: list[str] = []
    for state in states:
        if state not in normalized_states:
            normalized_states.append(state)
    if not normalized_states:
        normalized_states.append("unavailable")

    classification = max(
        normalized_states,
        key=lambda item: _CLASSIFICATION_PRIORITY.get(item, -1),
    )

    return {
        "classification": classification,
        "states": normalized_states,
        "provider_state": provider_state,
        "setup_state": setup_state,
        "operator_state": operator_state,
        "freshness_state": freshness_state,
        "summary": summary,
        "reasons": reasons or [],
        "generated_at": (generated_at or datetime.now(UTC)).isoformat(),
    }


def merge_truth(*truths: dict[str, Any], summary: str | None = None) -> dict[str, Any]:
    present = [truth for truth in truths if truth]
    if not present:
        return build_truth(
            states=["unavailable"],
            summary=summary or "Runtime truth is unavailable.",
            provider_state="unknown",
            setup_state="unknown",
            operator_state="unknown",
        )

    merged_states: list[str] = []
    merged_reasons: list[str] = []
    for truth in present:
        for state in truth.get("states", []):
            if state not in merged_states:
                merged_states.append(state)
        for reason in truth.get("reasons", []):
            if reason not in merged_reasons:
                merged_reasons.append(reason)

    freshest = [truth.get("freshness_state", "unknown") for truth in present]
    freshness_state = "unknown"
    if "stale" in freshest:
        freshness_state = "stale"
    elif "current" in freshest:
        freshness_state = "current"

    provider_state = next(
        (
            truth.get("provider_state")
            for truth in present
            if truth.get("provider_state") not in {None, "", "unknown"}
        ),
        "unknown",
    )
    setup_state = next(
        (
            truth.get("setup_state")
            for truth in present
            if truth.get("setup_state") not in {None, "", "unknown"}
        ),
        "unknown",
    )
    operator_state = next(
        (
            truth.get("operator_state")
            for truth in present
            if truth.get("operator_state") not in {None, "", "unknown"}
        ),
        "unknown",
    )

    return build_truth(
        states=merged_states,
        summary=summary or present[0].get("summary", "Runtime truth is available."),
        provider_state=provider_state,
        setup_state=setup_state,
        operator_state=operator_state,
        freshness_state=freshness_state,
        reasons=merged_reasons,
    )


def freshness_state_from_timestamp(
    value: str | datetime | None,
    *,
    stale_after: timedelta,
) -> str:
    if value is None:
        return "unknown"

    if isinstance(value, str):
        try:
            timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return "unknown"
    else:
        timestamp = value

    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    else:
        timestamp = timestamp.astimezone(UTC)

    if datetime.now(UTC) - timestamp > stale_after:
        return "stale"
    return "current"

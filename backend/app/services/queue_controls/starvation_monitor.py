from __future__ import annotations

from dataclasses import dataclass


WARNING_STARVATION_THRESHOLD = 3.0
CRITICAL_STARVATION_THRESHOLD = 5.0


@dataclass(frozen=True)
class StarvationStatus:
    starvation_score: float
    level: str


def compute_starvation_score(*, max_wait_seconds: float, target_wait_seconds: float) -> float:
    if target_wait_seconds <= 0:
        raise ValueError("target_wait_seconds must be greater than zero")
    return max_wait_seconds / target_wait_seconds


def evaluate_starvation(*, max_wait_seconds: float, target_wait_seconds: float) -> StarvationStatus:
    score = compute_starvation_score(max_wait_seconds=max_wait_seconds, target_wait_seconds=target_wait_seconds)
    if score >= CRITICAL_STARVATION_THRESHOLD:
        level = "critical"
    elif score >= WARNING_STARVATION_THRESHOLD:
        level = "warning"
    else:
        level = "ok"
    return StarvationStatus(starvation_score=score, level=level)


def emit_starvation_metric_stub(*, queue_name: str, starvation_score: float, level: str) -> None:
    _ = (queue_name, starvation_score, level)

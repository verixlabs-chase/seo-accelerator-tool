from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Awaitable, Callable
from typing import Any

from app.core.config import get_settings
from app.governance.replay.comparator import compare_confidence_bands, compare_hashes, compare_ordering, diff_payload
from app.governance.replay.schema import DriftEvent, ReplayCase
from app.services.queue_admission_service import shadow_replay_allowed

DriftEmitter = Callable[[DriftEvent], Awaitable[None]]
ReplayExecutor = Callable[[ReplayCase], Awaitable[dict[str, Any]]]

_VOLATILE_KEYS = {
    "generated_at",
    "request_id",
    "trace_id",
    "created_at",
    "updated_at",
    "detected_at",
}

_LOOP_SEMAPHORES: dict[int, tuple[int, asyncio.Semaphore]] = {}


def should_sample_shadow(*, stable_key: str, sample_rate_percent: float) -> bool:
    if sample_rate_percent <= 0:
        return False
    if sample_rate_percent > 100:
        raise ValueError("sample_rate_percent must be <= 100")
    digest = hashlib.sha256(stable_key.encode("utf-8")).hexdigest()
    bucket = int(digest[:8], 16) % 10_000
    threshold = int(sample_rate_percent * 100)
    return bucket < threshold


def _get_shadow_semaphore() -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    settings = get_settings()
    cap = max(1, int(settings.shadow_replay_max_concurrency))
    entry = _LOOP_SEMAPHORES.get(id(loop))
    if entry is None or entry[0] != cap:
        semaphore = asyncio.Semaphore(cap)
        _LOOP_SEMAPHORES[id(loop)] = (cap, semaphore)
        return semaphore
    return entry[1]


def _strip_volatile_fields(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {
            key: _strip_volatile_fields(value)
            for key, value in payload.items()
            if key not in _VOLATILE_KEYS
        }
    if isinstance(payload, list):
        return [_strip_volatile_fields(item) for item in payload]
    return payload


async def _run_shadow_replay_worker(
    case: ReplayCase,
    *,
    executor: ReplayExecutor,
    emit_drift: DriftEmitter,
) -> list[DriftEvent]:
    async with _get_shadow_semaphore():
        actual_output = await executor(case)

    expected_sanitized = _strip_volatile_fields(case.expected_output)
    actual_sanitized = _strip_volatile_fields(actual_output)
    drift_events: list[DriftEvent] = []

    hash_match, expected_hash, actual_hash = compare_hashes(expected_sanitized, actual_sanitized)
    if not hash_match:
        drift_events.append(
            DriftEvent(
                case_id=case.case_id,
                tenant_id=case.tenant_id,
                campaign_id=case.campaign_id,
                drift_type="hash",
                expected=expected_hash,
                actual=actual_hash,
                diff=diff_payload(expected_sanitized, actual_sanitized),
            )
        )

    ordering_match, expected_order, actual_order = compare_ordering(expected_sanitized, actual_sanitized)
    if not ordering_match:
        drift_events.append(
            DriftEvent(
                case_id=case.case_id,
                tenant_id=case.tenant_id,
                campaign_id=case.campaign_id,
                drift_type="ordering",
                expected=expected_order,
                actual=actual_order,
            )
        )

    bands_match, expected_bands, actual_bands = compare_confidence_bands(expected_sanitized, actual_sanitized)
    if not bands_match:
        drift_events.append(
            DriftEvent(
                case_id=case.case_id,
                tenant_id=case.tenant_id,
                campaign_id=case.campaign_id,
                drift_type="confidence_band",
                expected=expected_bands,
                actual=actual_bands,
            )
        )

    if drift_events:
        await asyncio.gather(*(emit_drift(event) for event in drift_events))

    return drift_events


def schedule_shadow_replay(
    case: ReplayCase,
    *,
    sample_rate_percent: float,
    executor: ReplayExecutor,
    emit_drift: DriftEmitter,
) -> asyncio.Task[list[DriftEvent]] | None:
    stable_key = f"{case.tenant_id}:{case.campaign_id}:{case.case_id}"
    if not shadow_replay_allowed():
        return None
    if not should_sample_shadow(stable_key=stable_key, sample_rate_percent=sample_rate_percent):
        return None

    loop = asyncio.get_running_loop()
    return loop.create_task(
        _run_shadow_replay_worker(case, executor=executor, emit_drift=emit_drift),
        name=f"shadow-replay:{stable_key}",
    )


async def run_shadow_replay(
    case: ReplayCase,
    *,
    sample_rate_percent: float,
    executor: ReplayExecutor,
    emit_drift: DriftEmitter,
) -> list[DriftEvent]:
    task = schedule_shadow_replay(
        case,
        sample_rate_percent=sample_rate_percent,
        executor=executor,
        emit_drift=emit_drift,
    )
    if task is None:
        return []
    return await task


async def emit_drift_stub(event: DriftEvent) -> None:
    _ = event

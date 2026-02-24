from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Awaitable, Callable
from typing import Any

from app.governance.replay.comparator import compare_confidence_bands, compare_hashes, compare_ordering, diff_payload
from app.governance.replay.schema import DriftEvent, ReplayCase
from app.services.queue_admission_service import shadow_replay_allowed

DriftEmitter = Callable[[DriftEvent], Awaitable[None]]
ReplayExecutor = Callable[[ReplayCase], Awaitable[dict[str, Any]]]


def should_sample_shadow(*, stable_key: str, sample_rate_percent: float) -> bool:
    if sample_rate_percent <= 0:
        return False
    if sample_rate_percent > 100:
        raise ValueError("sample_rate_percent must be <= 100")
    digest = hashlib.sha256(stable_key.encode("utf-8")).hexdigest()
    bucket = int(digest[:8], 16) % 10_000
    threshold = int(sample_rate_percent * 100)
    return bucket < threshold


async def run_shadow_replay(
    case: ReplayCase,
    *,
    sample_rate_percent: float,
    executor: ReplayExecutor,
    emit_drift: DriftEmitter,
) -> list[DriftEvent]:
    stable_key = f"{case.tenant_id}:{case.campaign_id}:{case.case_id}"
    if not shadow_replay_allowed():
        return []
    if not should_sample_shadow(stable_key=stable_key, sample_rate_percent=sample_rate_percent):
        return []

    actual_output = await executor(case)
    drift_events: list[DriftEvent] = []

    hash_match, expected_hash, actual_hash = compare_hashes(case.expected_output, actual_output)
    if not hash_match:
        drift_events.append(
            DriftEvent(
                case_id=case.case_id,
                tenant_id=case.tenant_id,
                campaign_id=case.campaign_id,
                drift_type="hash",
                expected=expected_hash,
                actual=actual_hash,
                diff=diff_payload(case.expected_output, actual_output),
            )
        )

    ordering_match, expected_order, actual_order = compare_ordering(case.expected_output, actual_output)
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

    bands_match, expected_bands, actual_bands = compare_confidence_bands(case.expected_output, actual_output)
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


async def emit_drift_stub(event: DriftEvent) -> None:
    _ = event

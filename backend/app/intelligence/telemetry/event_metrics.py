from __future__ import annotations

from typing import Any

from app.events.event_stream import checkpoint_offset, dead_letter_queue


def snapshot_event_metrics() -> dict[str, Any]:
    dead_letters = dead_letter_queue()
    checkpoint = checkpoint_offset()
    return {
        'consumer_checkpoint': checkpoint,
        'dead_letter_count': len(dead_letters),
        'event_lag': 0 if checkpoint is not None else len(dead_letters),
    }

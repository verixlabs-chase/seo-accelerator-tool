from __future__ import annotations

from app.intelligence.event_processors import feature_processor


def process(payload: dict[str, object]) -> dict[str, object] | None:
    return feature_processor.process(payload)

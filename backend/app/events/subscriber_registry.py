from __future__ import annotations

from app.events.event_bus import reset_subscribers, subscribe
from app.events.queue import enqueue_experiment_event, enqueue_learning_event
from app.events.event_types import EventType
from app.intelligence.event_processors import (
    execution_processor,
    outcome_processor,
    pattern_processor,
    recommendation_processor,
    signal_processor,
    simulation_processor,
)

_INITIALIZED = False


def register_default_subscribers(force_reset: bool = False) -> None:
    global _INITIALIZED
    if force_reset:
        reset_subscribers()
        _INITIALIZED = False

    if _INITIALIZED:
        return

    subscribe(EventType.SIGNAL_UPDATED.value, signal_processor.process)
    subscribe(EventType.FEATURE_UPDATED.value, pattern_processor.process)
    subscribe(EventType.PATTERN_DISCOVERED.value, recommendation_processor.process)
    subscribe(EventType.RECOMMENDATION_GENERATED.value, simulation_processor.process)
    subscribe(EventType.SIMULATION_COMPLETED.value, execution_processor.process)
    subscribe(EventType.EXECUTION_COMPLETED.value, outcome_processor.process)
    subscribe(EventType.OUTCOME_RECORDED.value, enqueue_learning_event)
    subscribe(EventType.EXPERIMENT_COMPLETED.value, enqueue_experiment_event)

    _INITIALIZED = True


def reset_registry() -> None:
    global _INITIALIZED
    reset_subscribers()
    _INITIALIZED = False

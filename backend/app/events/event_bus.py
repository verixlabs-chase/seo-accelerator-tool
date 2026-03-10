from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable
from threading import RLock
from typing import Any

from app.events.event_stream import initialize_event_stream, publish_event as publish_to_stream

logger = logging.getLogger('lsos.intelligence.event_bus')
EventHandler = Callable[[dict[str, Any]], None]


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)
        self._lock = RLock()
        initialize_event_stream()

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        with self._lock:
            handlers = self._handlers[event_type]
            if handler not in handlers:
                handlers.append(handler)

    def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        with self._lock:
            handlers = self._handlers.get(event_type)
            if not handlers:
                return
            self._handlers[event_type] = [item for item in handlers if item is not handler]

    def publish(self, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        envelope = publish_to_stream(event_type, payload)
        dispatch_payload = dict(payload)
        with self._lock:
            handlers = list(self._handlers.get(event_type, []))
        for handler in handlers:
            try:
                handler(dispatch_payload)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    'intelligence_event_handler_failed',
                    extra={'event_type': event_type, 'handler': getattr(handler, '__name__', repr(handler))},
                    exc_info=exc,
                )
        return envelope

    def reset(self) -> None:
        with self._lock:
            self._handlers.clear()


event_bus = EventBus()


def publish_event(event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    return event_bus.publish(event_type, payload)


def subscribe(event_type: str, handler: EventHandler) -> None:
    event_bus.subscribe(event_type, handler)


def unsubscribe(event_type: str, handler: EventHandler) -> None:
    event_bus.unsubscribe(event_type, handler)


def reset_subscribers() -> None:
    event_bus.reset()

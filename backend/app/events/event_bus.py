from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable
from threading import RLock
from typing import Any

logger = logging.getLogger('lsos.intelligence.event_bus')
EventHandler = Callable[[dict[str, Any]], None]


class InternalEventBus:
    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)
        self._lock = RLock()

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        with self._lock:
            handlers = self._handlers[event_type]
            if handler not in handlers:
                handlers.append(handler)

    def publish_event(self, event_type: str, payload: dict[str, Any]) -> None:
        with self._lock:
            handlers = list(self._handlers.get(event_type, []))

        for handler in handlers:
            try:
                handler(payload)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    'intelligence_event_handler_failed',
                    extra={
                        'event_type': event_type,
                        'handler': getattr(handler, '__name__', repr(handler)),
                    },
                    exc_info=exc,
                )

    def reset(self) -> None:
        with self._lock:
            self._handlers.clear()


_event_bus = InternalEventBus()


def publish_event(event_type: str, payload: dict[str, Any]) -> None:
    _event_bus.publish_event(event_type, payload)


def subscribe(event_type: str, handler: EventHandler) -> None:
    _event_bus.subscribe(event_type, handler)


def reset_subscribers() -> None:
    _event_bus.reset()

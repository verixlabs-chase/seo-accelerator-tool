from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable
from threading import RLock
from typing import Any


logger = logging.getLogger('lsos.event_bus')
EventHandler = Callable[[dict[str, Any]], None]


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)
        self._lock = RLock()

    def subscribe(self, event_name: str, handler: EventHandler) -> None:
        with self._lock:
            if handler not in self._handlers[event_name]:
                self._handlers[event_name].append(handler)

    def unsubscribe(self, event_name: str, handler: EventHandler) -> None:
        with self._lock:
            handlers = self._handlers.get(event_name)
            if not handlers:
                return
            self._handlers[event_name] = [item for item in handlers if item is not handler]

    def publish(self, event_name: str, payload: dict[str, Any]) -> None:
        with self._lock:
            handlers = list(self._handlers.get(event_name, []))
        for handler in handlers:
            try:
                handler(payload)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    'event_handler_failed',
                    extra={'event': event_name, 'handler': getattr(handler, '__name__', repr(handler))},
                    exc_info=exc,
                )


SUPPORTED_EVENTS = {
    'tenant.created',
    'campaign.created',
    'provider.connected',
    'crawl.started',
    'crawl.completed',
    'report.generated',
    'automation.enabled',
}


event_bus = EventBus()
for _event_name in SUPPORTED_EVENTS:
    event_bus._handlers.setdefault(_event_name, [])

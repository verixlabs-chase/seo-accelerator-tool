from __future__ import annotations

# Backward-compatible import surface for the canonical app.events bus.
from app.events.event_bus import EventBus, event_bus

SUPPORTED_EVENTS = {
    'tenant.created',
    'campaign.created',
    'provider.connected',
    'crawl.started',
    'crawl.completed',
    'report.generated',
    'automation.enabled',
}

for _event_name in SUPPORTED_EVENTS:
    event_bus._handlers.setdefault(_event_name, [])


__all__ = ['EventBus', 'event_bus', 'SUPPORTED_EVENTS']

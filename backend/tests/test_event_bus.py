from app.core.event_bus import EventBus
from app.events.event_bus import publish_event, reset_subscribers, subscribe
from app.events.event_types import EventType


def test_core_event_bus_publish_and_subscribe() -> None:
    bus = EventBus()
    events: list[dict] = []

    def _handler(payload: dict) -> None:
        events.append(payload)

    bus.subscribe('crawl.completed', _handler)
    bus.publish('crawl.completed', {'campaign_id': 'c-1'})

    assert events == [{'campaign_id': 'c-1'}]


def test_core_event_bus_unsubscribe() -> None:
    bus = EventBus()
    events: list[dict] = []

    def _handler(payload: dict) -> None:
        events.append(payload)

    bus.subscribe('report.generated', _handler)
    bus.unsubscribe('report.generated', _handler)
    bus.publish('report.generated', {'report_id': 'r-1'})

    assert events == []


def test_internal_event_bus_dispatches_handlers() -> None:
    reset_subscribers()
    seen: list[dict] = []

    def _handler(payload: dict) -> None:
        seen.append(payload)

    subscribe(EventType.SIGNAL_UPDATED.value, _handler)
    publish_event(EventType.SIGNAL_UPDATED.value, {'campaign_id': 'c1', 'signals': {'avg_rank': 8.2}})

    assert seen == [{'campaign_id': 'c1', 'signals': {'avg_rank': 8.2}}]

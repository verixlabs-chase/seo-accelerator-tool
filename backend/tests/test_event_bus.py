from app.core.event_bus import EventBus


def test_event_bus_publish_and_subscribe() -> None:
    bus = EventBus()
    events: list[dict] = []

    def _handler(payload: dict) -> None:
        events.append(payload)

    bus.subscribe('crawl.completed', _handler)
    bus.publish('crawl.completed', {'campaign_id': 'c-1'})

    assert events == [{'campaign_id': 'c-1'}]


def test_event_bus_unsubscribe() -> None:
    bus = EventBus()
    events: list[dict] = []

    def _handler(payload: dict) -> None:
        events.append(payload)

    bus.subscribe('report.generated', _handler)
    bus.unsubscribe('report.generated', _handler)
    bus.publish('report.generated', {'report_id': 'r-1'})

    assert events == []


def test_event_bus_handler_failure_is_non_fatal() -> None:
    bus = EventBus()
    calls = {'ok': 0}

    def _bad(_: dict) -> None:
        raise RuntimeError('boom')

    def _ok(_: dict) -> None:
        calls['ok'] += 1

    bus.subscribe('automation.enabled', _bad)
    bus.subscribe('automation.enabled', _ok)
    bus.publish('automation.enabled', {'campaign_id': 'c-1'})

    assert calls['ok'] == 1

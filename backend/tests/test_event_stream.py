from app.events.event_stream import checkpoint_offset, consume_events, dead_letter_queue, publish_event, reset_test_event_stream


def test_event_stream_publish_consume_ack_cycle() -> None:
    reset_test_event_stream()
    published = publish_event('signal.updated', {'campaign_id': 'camp-1'})
    handled: list[str] = []

    def handler(event: dict[str, object]) -> None:
        handled.append(str(event['event_id']))

    consume_events(handler)

    assert handled == [str(published['event_id'])]
    assert checkpoint_offset() == '1'


def test_event_stream_dead_letters_after_retries() -> None:
    reset_test_event_stream()
    event = publish_event('signal.updated', {'campaign_id': 'camp-2'})

    def handler(_event: dict[str, object]) -> None:
        raise RuntimeError('boom')

    consume_events(handler)
    consume_events(handler)
    consume_events(handler)

    letters = dead_letter_queue()
    assert letters
    assert letters[0]['event_id'] == event['event_id']

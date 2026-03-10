from __future__ import annotations

import json
import logging
import threading
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Callable

from redis.exceptions import RedisError

from app.core.config import get_settings
from app.core.metrics import event_batch_latency_seconds
from app.db.redis_client import get_redis_client

logger = logging.getLogger('lsos.intelligence.event_stream')

STREAM_KEY = 'lsos:intelligence:events'
GROUP_NAME = 'lsos-intelligence'
DLQ_STREAM_KEY = 'lsos:intelligence:events:dlq'
STATE_PREFIX = 'lsos:intelligence:event_state'
CHECKPOINT_PREFIX = 'lsos:intelligence:event_checkpoint'
PROCESSED_PREFIX = 'lsos:intelligence:event_processed'
MAX_RETRIES = 3

EventHandler = Callable[[dict[str, Any]], None]


@dataclass(slots=True)
class EventRecord:
    event_id: str
    event_type: str
    payload: dict[str, Any]
    stream_id: str
    attempts: int
    created_at: str


class _InMemoryEventStream:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._events: deque[EventRecord] = deque()
        self._inflight: dict[str, EventRecord] = {}
        self._processed: set[str] = set()
        self._dead_letters: list[EventRecord] = []
        self._counter = 0

    def publish_event(self, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            self._counter += 1
            event_id = str(payload.get('event_id') or uuid.uuid4())
            record = EventRecord(
                event_id=event_id,
                event_type=event_type,
                payload=dict(payload),
                stream_id=f'test-{self._counter}',
                attempts=0,
                created_at=datetime.now(UTC).isoformat(),
            )
            self._events.append(record)
            return _record_to_dict(record)

    def consume_events(self, handler: EventHandler, *, consumer_name: str = 'default', max_count: int = 10) -> list[str]:
        del consumer_name
        handled: list[str] = []
        for _ in range(max(1, int(max_count))):
            with self._lock:
                if not self._events:
                    break
                record = self._events.popleft()
                if record.event_id in self._processed:
                    continue
                record = EventRecord(
                    event_id=record.event_id,
                    event_type=record.event_type,
                    payload=dict(record.payload),
                    stream_id=record.stream_id,
                    attempts=record.attempts + 1,
                    created_at=record.created_at,
                )
                self._inflight[record.event_id] = record
            try:
                handler(_record_to_dict(record))
                self.acknowledge_event(record.event_id)
                handled.append(record.event_id)
            except Exception:  # noqa: BLE001
                self._handle_failure(record)
        return handled

    def acknowledge_event(self, event_id: str) -> bool:
        with self._lock:
            record = self._inflight.pop(event_id, None)
            if record is None:
                return False
            self._processed.add(event_id)
            return True

    def retry_failed_events(self) -> int:
        with self._lock:
            failed = list(self._inflight.values())
            self._inflight.clear()
        for record in failed:
            self._handle_failure(record)
        return len(failed)

    def dead_letter_queue(self) -> list[dict[str, Any]]:
        with self._lock:
            return [_record_to_dict(item) for item in self._dead_letters]

    def checkpoint_offset(self, consumer_name: str) -> str:
        del consumer_name
        with self._lock:
            if not self._processed:
                return '0-0'
            return str(len(self._processed))

    def reset(self) -> None:
        with self._lock:
            self._events.clear()
            self._inflight.clear()
            self._processed.clear()
            self._dead_letters.clear()
            self._counter = 0

    def _handle_failure(self, record: EventRecord) -> None:
        with self._lock:
            self._inflight.pop(record.event_id, None)
            if record.attempts >= MAX_RETRIES:
                self._dead_letters.append(record)
            else:
                self._events.append(record)


class RedisEventStream:
    def __init__(self) -> None:
        self._group_initialized = False
        self._lock = threading.RLock()

    def publish_event(self, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        client = self._client()
        event_id = str(payload.get('event_id') or uuid.uuid4())
        body = {
            'event_id': event_id,
            'event_type': event_type,
            'payload_json': json.dumps(payload, sort_keys=True),
            'created_at': datetime.now(UTC).isoformat(),
            'attempts': '0',
        }
        stream_id = client.xadd(STREAM_KEY, body)
        client.hset(self._state_key(event_id), mapping={'status': 'published', 'stream_id': stream_id, 'attempts': 0})
        return {
            'event_id': event_id,
            'event_type': event_type,
            'payload': dict(payload),
            'stream_id': stream_id,
            'attempts': 0,
            'created_at': body['created_at'],
        }

    def consume_events(self, handler: EventHandler, *, consumer_name: str = 'default', max_count: int = 10) -> list[str]:
        client = self._client()
        self._ensure_group(client)
        response = client.xreadgroup(
            groupname=GROUP_NAME,
            consumername=consumer_name,
            streams={STREAM_KEY: '>'},
            count=max(1, int(max_count)),
            block=100,
        )
        handled: list[str] = []
        for _stream_name, events in response or []:
            for stream_id, fields in events:
                record = self._decode_record(stream_id, fields)
                if client.sismember(self._processed_key(consumer_name), record.event_id):
                    self.acknowledge_event(record.event_id, consumer_name=consumer_name, stream_id=stream_id)
                    continue
                try:
                    handler(_record_to_dict(record))
                    self.acknowledge_event(record.event_id, consumer_name=consumer_name, stream_id=stream_id)
                    handled.append(record.event_id)
                except Exception as exc:  # noqa: BLE001
                    self._mark_failure(client, record, consumer_name=consumer_name, stream_id=stream_id, error=str(exc))
        return handled

    def acknowledge_event(self, event_id: str, *, consumer_name: str = 'default', stream_id: str | None = None) -> bool:
        client = self._client()
        if stream_id is None:
            stream_id = self._stream_id_for_event(client, event_id)
        if not stream_id:
            return False
        client.xack(STREAM_KEY, GROUP_NAME, stream_id)
        client.sadd(self._processed_key(consumer_name), event_id)
        client.set(self._checkpoint_key(consumer_name), stream_id)
        client.hset(self._state_key(event_id), mapping={'status': 'acked', 'acked_at': datetime.now(UTC).isoformat()})
        return True

    def retry_failed_events(self) -> int:
        client = self._client()
        self._ensure_group(client)
        pending = client.xpending_range(STREAM_KEY, GROUP_NAME, min='-', max='+', count=100)
        retried = 0
        for item in pending:
            stream_id = item.get('message_id')
            if not stream_id:
                continue
            entries = client.xrange(STREAM_KEY, min=stream_id, max=stream_id, count=1)
            if not entries:
                continue
            _, fields = entries[0]
            record = self._decode_record(stream_id, fields)
            attempts = int(client.hget(self._state_key(record.event_id), 'attempts') or 0)
            if attempts >= MAX_RETRIES:
                self._send_to_dead_letter(client, record, reason='max_retries_exceeded')
                client.xack(STREAM_KEY, GROUP_NAME, stream_id)
                continue
            client.xclaim(STREAM_KEY, GROUP_NAME, 'retry-consumer', min_idle_time=0, message_ids=[stream_id])
            client.hset(self._state_key(record.event_id), mapping={'status': 'retry_pending'})
            retried += 1
        return retried

    def dead_letter_queue(self) -> list[dict[str, Any]]:
        client = self._client()
        rows = client.xrevrange(DLQ_STREAM_KEY, count=100)
        payloads: list[dict[str, Any]] = []
        for stream_id, fields in rows:
            record = self._decode_record(stream_id, fields)
            payloads.append(_record_to_dict(record))
        return payloads

    def checkpoint_offset(self, consumer_name: str) -> str:
        client = self._client()
        return (client.get(self._checkpoint_key(consumer_name)) or b'0-0').decode('utf-8') if isinstance(client.get(self._checkpoint_key(consumer_name)), bytes) else str(client.get(self._checkpoint_key(consumer_name)) or '0-0')

    def ensure_initialized(self) -> None:
        self._ensure_group(self._client())

    def _client(self):
        client = get_redis_client()
        if client is None:
            raise RuntimeError('Redis event stream unavailable in test mode.')
        return client

    def _ensure_group(self, client) -> None:
        with self._lock:
            if self._group_initialized:
                return
            try:
                client.xgroup_create(STREAM_KEY, GROUP_NAME, id='0-0', mkstream=True)
            except RedisError:
                pass
            self._group_initialized = True

    def _decode_record(self, stream_id: str, fields: dict[str, Any]) -> EventRecord:
        def _decode(value: Any) -> str:
            return value.decode('utf-8') if isinstance(value, bytes) else str(value)
        payload_raw = fields.get('payload_json', '{}')
        payload_raw = _decode(payload_raw)
        try:
            payload = json.loads(payload_raw)
        except json.JSONDecodeError:
            payload = {}
        return EventRecord(
            event_id=_decode(fields.get('event_id', '')),
            event_type=_decode(fields.get('event_type', '')),
            payload=payload if isinstance(payload, dict) else {},
            stream_id=stream_id.decode('utf-8') if isinstance(stream_id, bytes) else str(stream_id),
            attempts=int(_decode(fields.get('attempts', '0')) or 0),
            created_at=_decode(fields.get('created_at', datetime.now(UTC).isoformat())),
        )

    def _mark_failure(self, client, record: EventRecord, *, consumer_name: str, stream_id: str, error: str) -> None:
        state_key = self._state_key(record.event_id)
        attempts = int(client.hget(state_key, 'attempts') or 0) + 1
        client.hset(state_key, mapping={'status': 'failed', 'attempts': attempts, 'last_error': error, 'last_failed_at': datetime.now(UTC).isoformat()})
        if attempts >= MAX_RETRIES:
            self._send_to_dead_letter(client, record, reason=error)
            client.xack(STREAM_KEY, GROUP_NAME, stream_id)
        else:
            client.srem(self._processed_key(consumer_name), record.event_id)

    def _send_to_dead_letter(self, client, record: EventRecord, *, reason: str) -> None:
        client.xadd(
            DLQ_STREAM_KEY,
            {
                'event_id': record.event_id,
                'event_type': record.event_type,
                'payload_json': json.dumps(record.payload, sort_keys=True),
                'created_at': record.created_at,
                'attempts': str(record.attempts),
                'reason': reason,
            },
        )
        client.hset(self._state_key(record.event_id), mapping={'status': 'dead_lettered', 'reason': reason})

    def _stream_id_for_event(self, client, event_id: str) -> str | None:
        value = client.hget(self._state_key(event_id), 'stream_id')
        if value is None:
            return None
        return value.decode('utf-8') if isinstance(value, bytes) else str(value)

    def _state_key(self, event_id: str) -> str:
        return f'{STATE_PREFIX}:{event_id}'

    def _checkpoint_key(self, consumer_name: str) -> str:
        return f'{CHECKPOINT_PREFIX}:{consumer_name}'

    def _processed_key(self, consumer_name: str) -> str:
        return f'{PROCESSED_PREFIX}:{consumer_name}'


_LOCAL_STREAM = _InMemoryEventStream()
_REDIS_STREAM = RedisEventStream()


def _use_local() -> bool:
    return get_settings().app_env.lower() == 'test'


def get_event_stream() -> _InMemoryEventStream | RedisEventStream:
    return _LOCAL_STREAM if _use_local() else _REDIS_STREAM


def initialize_event_stream() -> None:
    stream = get_event_stream()
    if hasattr(stream, 'ensure_initialized'):
        stream.ensure_initialized()


def publish_event(event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    return get_event_stream().publish_event(event_type, payload)


def consume_events(handler: EventHandler, *, consumer_name: str = 'default', max_count: int = 10) -> list[str]:
    return get_event_stream().consume_events(handler, consumer_name=consumer_name, max_count=max_count)


def acknowledge_event(event_id: str, *, consumer_name: str = 'default', stream_id: str | None = None) -> bool:
    stream = get_event_stream()
    if isinstance(stream, _InMemoryEventStream):
        return stream.acknowledge_event(event_id)
    return stream.acknowledge_event(event_id, consumer_name=consumer_name, stream_id=stream_id)


def retry_failed_events() -> int:
    return get_event_stream().retry_failed_events()


def dead_letter_queue() -> list[dict[str, Any]]:
    return get_event_stream().dead_letter_queue()


def checkpoint_offset(consumer_name: str = 'default') -> str:
    return get_event_stream().checkpoint_offset(consumer_name)


def reset_test_event_stream() -> None:
    _LOCAL_STREAM.reset()


def _record_to_dict(record: EventRecord) -> dict[str, Any]:
    return {
        'event_id': record.event_id,
        'event_type': record.event_type,
        'payload': dict(record.payload),
        'stream_id': record.stream_id,
        'attempts': record.attempts,
        'created_at': record.created_at,
    }


def consume_event_batches(
    handler: EventHandler,
    *,
    consumer_name: str = 'default',
    batch_size: int | None = None,
    max_batches: int = 1,
) -> list[list[str]]:
    configured_size = int(batch_size or get_settings().event_stream_batch_size)
    effective_batch_size = max(50, min(configured_size, 200))
    batches: list[list[str]] = []
    for _ in range(max(1, int(max_batches))):
        started_at = datetime.now(UTC)
        handled = consume_events(handler, consumer_name=consumer_name, max_count=effective_batch_size)
        if not handled:
            break
        elapsed = max((datetime.now(UTC) - started_at).total_seconds(), 0.0)
        event_batch_latency_seconds.labels(consumer_name=consumer_name).observe(elapsed)
        batches.append(handled)
    return batches


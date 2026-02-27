from app.services.strategy_engine.decision_trace import (
    compute_trace_hash,
    serialize_trace_payload,
)


def test_trace_serialization_deterministic() -> None:
    payload_a = {'b': 1, 'a': 2}
    payload_b = {'a': 2, 'b': 1}

    serialized_a = serialize_trace_payload(payload_a)
    serialized_b = serialize_trace_payload(payload_b)

    assert serialized_a == serialized_b
    assert compute_trace_hash(payload_a) == compute_trace_hash(payload_b)
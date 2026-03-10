from __future__ import annotations


def process(payload: dict[str, object]) -> dict[str, object]:
    return {
        'status': 'noop',
        'worker': 'learning',
        'legacy_pipeline_active': False,
        'payload': dict(payload),
    }

from __future__ import annotations


def process(payload: dict[str, object]) -> dict[str, object]:
    delta = float(payload.get('delta', 0.0) or 0.0)
    if delta > 0.01:
        direction = 'improved'
    elif delta < -0.01:
        direction = 'declined'
    else:
        direction = 'no_material_change'
    return {
        'status': 'observed',
        'worker': 'learning',
        'legacy_pipeline_active': False,
        'mode': 'observation_only',
        'policy_updates_applied': 0,
        'causal_claim_created': False,
        'observation': {
            'outcome_id': payload.get('outcome_id'),
            'campaign_id': payload.get('campaign_id'),
            'recommendation_id': payload.get('recommendation_id'),
            'measurement_kind': payload.get('measurement_kind', 'execution_metric'),
            'delta': delta,
            'direction': direction,
        },
        'payload': dict(payload),
    }

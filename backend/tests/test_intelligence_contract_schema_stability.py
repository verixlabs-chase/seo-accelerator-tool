from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.intelligence.contracts.features import FeatureBundle, FeaturePayload
from app.intelligence.contracts.mutations import MutationBundle, MutationPayload
from app.intelligence.contracts.outcomes import OutcomeBundle, OutcomePayload
from app.intelligence.contracts.patterns import PatternBundle, PatternPayload
from app.intelligence.contracts.policies import PolicyBundle, PolicyPayload
from app.intelligence.contracts.recommendations import (
    RecommendationBundle,
    RecommendationPayload,
    maybe_validate_recommendation_artifact,
)
from app.intelligence.contracts.signals import SignalBatch, SignalPayload
from app.intelligence.intelligence_orchestrator import _validated_recommendation_payload


EXPECTED_RECOMMENDATION_FIELDS = [
    'policy_id',
    'recommendation_type',
    'rationale',
    'confidence',
    'evidence',
    'risk_tier',
    'rollback_plan',
]

EXPECTED_RECOMMENDATION_JSON_SCHEMA = {
    'additionalProperties': False,
    'properties': {
        'confidence': {'maximum': 1.0, 'minimum': 0.0, 'title': 'Confidence', 'type': 'number'},
        'evidence': {'additionalProperties': True, 'title': 'Evidence', 'type': 'object'},
        'policy_id': {'minLength': 1, 'title': 'Policy Id', 'type': 'string'},
        'rationale': {'minLength': 1, 'title': 'Rationale', 'type': 'string'},
        'recommendation_type': {'minLength': 1, 'title': 'Recommendation Type', 'type': 'string'},
        'risk_tier': {'maximum': 4, 'minimum': 0, 'title': 'Risk Tier', 'type': 'integer'},
        'rollback_plan': {'additionalProperties': True, 'title': 'Rollback Plan', 'type': 'object'},
    },
    'required': EXPECTED_RECOMMENDATION_FIELDS,
    'title': 'RecommendationPayload',
    'type': 'object',
}


def test_contract_modules_construct_stable_payload_types() -> None:
    assert SignalBatch(signals=[SignalPayload(signal_name='traffic', source='ga', value=12.0)]).signals[0].signal_name == 'traffic'
    assert FeatureBundle(features=[FeaturePayload(feature_name='ctr', value=0.2)]).features[0].feature_name == 'ctr'
    assert PatternBundle(patterns=[PatternPayload(pattern_key='legacy::drop', confidence=0.6)]).patterns[0].pattern_key == 'legacy::drop'
    assert PolicyBundle(policies=[PolicyPayload(policy_id='legacy::policy', rationale='reason', priority_weight=0.5)]).policies[0].policy_id == 'legacy::policy'
    assert MutationBundle(mutations=[MutationPayload(mutation_type='title', target_id='page-1')]).mutations[0].target_id == 'page-1'
    assert OutcomeBundle(outcomes=[OutcomePayload(recommendation_type='policy::legacy', outcome_type='completed')]).outcomes[0].outcome_type == 'completed'
    assert RecommendationBundle(recommendations=[_valid_payload()]).recommendations[0].policy_id == 'legacy::gbp_low_review_velocity'


def test_recommendation_payload_schema_stability() -> None:
    assert list(RecommendationPayload.model_fields.keys()) == EXPECTED_RECOMMENDATION_FIELDS


def test_recommendation_payload_validation() -> None:
    payload = RecommendationPayload.model_validate(_valid_payload())
    assert payload.policy_id == 'legacy::gbp_low_review_velocity'
    assert payload.evidence['pattern_key'] == 'legacy_scenario::gbp_low_review_velocity'

    with pytest.raises(ValidationError):
        RecommendationPayload.model_validate({key: value for key, value in _valid_payload().items() if key != 'policy_id'})

    with pytest.raises(ValidationError):
        RecommendationPayload.model_validate({**_valid_payload(), 'confidence': 1.5})

    with pytest.raises(ValidationError):
        RecommendationPayload.model_validate({**_valid_payload(), 'evidence': ['legacy_scenario::gbp_low_review_velocity']})

    with pytest.raises(ValidationError):
        RecommendationPayload.model_validate({**_valid_payload(), 'risk_tier': '2'})


def test_contract_serialization_stability() -> None:
    payload = RecommendationPayload.model_validate(_valid_payload())
    dumped = payload.model_dump()
    restored = RecommendationPayload(**dumped)

    assert restored == payload
    assert restored.model_dump() == dumped


def test_orchestrator_contract_compliance() -> None:
    payload = _validated_recommendation_payload(
        recommendation={
            'rationale': 'Low review acquisition velocity detected.',
            'priority_weight': 0.42,
            'risk_tier': 2,
            'evidence': {'pattern_key': 'legacy_scenario::gbp_low_review_velocity'},
            'rollback_plan': {'steps': ['revert_automation_action']},
        },
        policy_id='legacy::gbp_low_review_velocity',
        recommendation_type='policy::legacy::gbp_low_review_velocity',
        action='revert_automation_action',
        all_patterns=[],
    )

    assert isinstance(payload, RecommendationPayload)
    assert payload.model_dump() == _valid_payload()


def test_replay_contract_compatibility() -> None:
    replay_output = {
        'campaign_id': 'campaign-1',
        'recommendations': [_valid_payload()],
    }

    validated = maybe_validate_recommendation_artifact(replay_output)

    assert validated['recommendations'][0] == _valid_payload()


def test_recommendation_payload_json_schema_snapshot() -> None:
    schema = RecommendationPayload.model_json_schema()
    assert schema == EXPECTED_RECOMMENDATION_JSON_SCHEMA
    assert json.dumps(schema, sort_keys=True) == json.dumps(EXPECTED_RECOMMENDATION_JSON_SCHEMA, sort_keys=True)


def _valid_payload() -> dict[str, object]:
    return {
        'policy_id': 'legacy::gbp_low_review_velocity',
        'recommendation_type': 'policy::legacy::gbp_low_review_velocity',
        'rationale': 'Low review acquisition velocity detected.',
        'confidence': 0.42,
        'evidence': {'pattern_key': 'legacy_scenario::gbp_low_review_velocity'},
        'risk_tier': 2,
        'rollback_plan': {'steps': ['revert_automation_action']},
    }

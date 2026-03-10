from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.intelligence.contracts.recommendations import (
    RecommendationPayload,
    maybe_validate_recommendation_artifact,
)
from app.intelligence.intelligence_orchestrator import _validated_recommendation_payload


def test_recommendation_payload_accepts_valid_contract() -> None:
    payload = RecommendationPayload.model_validate(
        {
            'policy_id': 'prioritize_internal_linking',
            'recommendation_type': 'policy::prioritize_internal_linking::add_contextual_links',
            'rationale': 'Link equity is fragmented across orphaned pages.',
            'confidence': 0.82,
            'evidence': {'pattern_key': 'internal_link_gap'},
            'risk_tier': 1,
            'rollback_plan': {'steps': ['restore_internal_links']},
        }
    )

    assert payload.policy_id == 'prioritize_internal_linking'
    assert payload.risk_tier == 1


def test_recommendation_payload_rejects_malformed_contract() -> None:
    with pytest.raises(ValidationError):
        RecommendationPayload.model_validate(
            {
                'policy_id': 'prioritize_internal_linking',
                'recommendation_type': 'policy::prioritize_internal_linking::add_contextual_links',
                'rationale': 'Missing rollback plan and invalid confidence.',
                'confidence': 1.5,
                'evidence': {'pattern_key': 'internal_link_gap'},
                'risk_tier': 1,
            }
        )


def test_orchestrator_contract_helper_normalizes_defaults() -> None:
    payload = _validated_recommendation_payload(
        recommendation={'priority_weight': 0.64},
        policy_id='fallback',
        recommendation_type='policy::fallback::stabilize_foundations',
        action='stabilize_foundations',
        all_patterns=[],
    )

    assert payload.policy_id == 'fallback'
    assert payload.recommendation_type == 'policy::fallback::stabilize_foundations'
    assert payload.rollback_plan == {'steps': ['revert_automation_action']}
    assert payload.evidence['pattern_key'] == 'orchestrator.default'


def test_replay_contract_validation_normalizes_contract_recommendations() -> None:
    payload = maybe_validate_recommendation_artifact(
        {
            'campaign_id': 'campaign-1',
            'recommendations': [
                {
                    'policy_id': 'prioritize_internal_linking',
                    'recommendation_type': 'policy::prioritize_internal_linking::add_contextual_links',
                    'rationale': 'Link equity is fragmented across orphaned pages.',
                    'confidence': 0.82,
                    'evidence': {'pattern_key': 'internal_link_gap'},
                    'risk_tier': 1,
                    'rollback_plan': {'steps': ['restore_internal_links']},
                }
            ],
        }
    )

    assert payload['recommendations'][0]['policy_id'] == 'prioritize_internal_linking'


def test_replay_contract_validation_ignores_legacy_strategy_payloads() -> None:
    payload = {
        'campaign_id': 'campaign-1',
        'recommendations': [
            {
                'scenario_id': 'cwv_lcp_degraded',
                'priority_score': 0.9,
                'confidence': 0.8,
                'evidence': [],
                'impact_level': 'high',
            }
        ],
    }

    assert maybe_validate_recommendation_artifact(payload) == payload

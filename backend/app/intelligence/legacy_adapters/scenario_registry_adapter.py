from __future__ import annotations

from typing import Any

from app.services.strategy_engine.scenario_registry import SCENARIO_INDEX
from app.services.strategy_engine.schemas import DiagnosticResult

_IMPACT_TO_RISK_TIER = {
    'low': 1,
    'medium': 2,
    'high': 2,
}


def diagnostics_to_patterns(diagnostics: list[DiagnosticResult]) -> list[dict[str, Any]]:
    patterns: list[dict[str, Any]] = []
    for item in diagnostics:
        scenario = SCENARIO_INDEX.get(item.scenario_id)
        if scenario is None:
            continue
        patterns.append(
            {
                'pattern_key': f'legacy_scenario::{item.scenario_id}',
                'confidence': float(item.confidence),
                'evidence': [e.signal_name for e in item.evidence],
                'legacy_scenario_id': item.scenario_id,
                'legacy_category': scenario.category,
                'source': 'legacy_strategy_engine',
            }
        )
    return patterns


def diagnostics_to_policy_inputs(diagnostics: list[DiagnosticResult]) -> list[dict[str, Any]]:
    policy_inputs: list[dict[str, Any]] = []
    for item in diagnostics:
        scenario = SCENARIO_INDEX.get(item.scenario_id)
        if scenario is None or scenario.deprecated:
            continue
        base_priority = max(0.05, min(1.0, float(scenario.impact_weight) * float(item.signal_magnitude)))
        policy_inputs.append(
            {
                'policy_id': f'legacy::{item.scenario_id}',
                'priority_weight': round(base_priority, 6),
                'risk_tier': _IMPACT_TO_RISK_TIER.get(scenario.impact_level.lower(), 2),
                'recommended_actions': list(scenario.recommended_actions),
                'source_patterns': [f'legacy_scenario::{item.scenario_id}'],
                'pattern_confidence': float(item.confidence),
                'legacy_source_scenario_id': item.scenario_id,
                'rationale': scenario.diagnosis,
                'operator_explanation': {
                    'diagnosis': scenario.diagnosis,
                    'root_cause': scenario.root_cause,
                    'expected_outcome': scenario.expected_outcome,
                    'authoritative_sources': list(scenario.authoritative_sources),
                    'impact_level': scenario.impact_level,
                    'evidence': [
                        {
                            'signal_name': evidence.signal_name,
                            'signal_value': evidence.signal_value,
                            'threshold_reference': evidence.threshold_reference,
                            'comparator': evidence.comparator,
                            'comparative_value': evidence.comparative_value,
                            'window_reference': evidence.window_reference,
                        }
                        for evidence in item.evidence
                    ],
                },
            }
        )
    return policy_inputs

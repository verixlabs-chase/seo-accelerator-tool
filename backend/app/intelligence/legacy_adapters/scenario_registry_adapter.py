from __future__ import annotations

from typing import Any

from app.intelligence.lexicon.loader import get_builtin_lexicon
from app.intelligence.lexicon.schema import DiagnosticDefinition, IntelligenceLexicon
from app.services.strategy_engine.schemas import DiagnosticResult

_IMPACT_TO_RISK_TIER = {
    "low": 1,
    "medium": 2,
    "high": 2,
}


def diagnostics_to_patterns(
    diagnostics: list[DiagnosticResult],
    *,
    lexicon: IntelligenceLexicon | None = None,
) -> list[dict[str, Any]]:
    resolved_lexicon = lexicon or get_builtin_lexicon()
    patterns: list[dict[str, Any]] = []
    for item in diagnostics:
        scenario = resolved_lexicon.diagnostic_index.get(item.scenario_id)
        if scenario is None:
            continue
        patterns.append(
            {
                "pattern_key": f"legacy_scenario::{item.scenario_id}",
                "confidence": float(item.confidence),
                "evidence": [e.signal_name for e in item.evidence],
                "legacy_scenario_id": item.scenario_id,
                "legacy_category": scenario.category,
                "source": "deterministic_diagnostic_engine",
                "lexicon_version": resolved_lexicon.meta.version,
            }
        )
    return patterns


def diagnostics_to_policy_inputs(
    diagnostics: list[DiagnosticResult],
    *,
    lexicon: IntelligenceLexicon | None = None,
) -> list[dict[str, Any]]:
    resolved_lexicon = lexicon or get_builtin_lexicon()
    policy_inputs: list[dict[str, Any]] = []
    for item in diagnostics:
        scenario = resolved_lexicon.diagnostic_index.get(item.scenario_id)
        if scenario is None or scenario.deprecated:
            continue
        base_priority = max(
            0.05, min(1.0, float(scenario.impact_weight) * float(item.signal_magnitude))
        )
        policy_inputs.append(
            {
                "policy_id": f"legacy::{item.scenario_id}",
                "priority_weight": round(base_priority, 6),
                "risk_tier": _IMPACT_TO_RISK_TIER.get(scenario.impact_level.lower(), 2),
                "recommended_actions": _runtime_action_tokens(
                    resolved_lexicon,
                    scenario,
                ),
                "source_patterns": [f"legacy_scenario::{item.scenario_id}"],
                "pattern_confidence": float(item.confidence),
                "legacy_source_scenario_id": item.scenario_id,
                "rationale": scenario.diagnosis,
                "lexicon_version": resolved_lexicon.meta.version,
                "operator_explanation": {
                    "diagnostic_id": scenario.diagnostic_id,
                    "diagnosis": scenario.diagnosis,
                    "root_cause": scenario.root_cause_hypotheses[0],
                    "root_cause_hypotheses": list(scenario.root_cause_hypotheses),
                    "expected_outcome": scenario.expected_outcome,
                    "authoritative_sources": _source_urls(resolved_lexicon, scenario),
                    "impact_level": scenario.impact_level,
                    "action_ids": list(scenario.action_ids),
                    "lexicon_version": resolved_lexicon.meta.version,
                    "evidence": [
                        {
                            "signal_name": evidence.signal_name,
                            "signal_value": evidence.signal_value,
                            "threshold_reference": evidence.threshold_reference,
                            "comparator": evidence.comparator,
                            "comparative_value": evidence.comparative_value,
                            "window_reference": evidence.window_reference,
                        }
                        for evidence in item.evidence
                    ],
                },
            }
        )
    return policy_inputs


def _runtime_action_tokens(
    lexicon: IntelligenceLexicon,
    diagnostic: DiagnosticDefinition,
) -> list[str]:
    # Stable machine IDs make recommendations deterministic and give the AI
    # layer an allow-list. Human-facing copy is resolved from the same IDs.
    return [action_id for action_id in diagnostic.action_ids if action_id in lexicon.action_index]


def _source_urls(
    lexicon: IntelligenceLexicon,
    diagnostic: DiagnosticDefinition,
) -> list[str]:
    return [
        str(lexicon.source_index[source_id].url)
        for source_id in diagnostic.source_ids
        if source_id in lexicon.source_index
    ]

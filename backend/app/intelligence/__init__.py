from __future__ import annotations

from importlib import import_module
from typing import Any

_EXPORTS = {
    "assemble_signals": ("app.intelligence.signal_assembler", "assemble_signals"),
    "write_temporal_signals": ("app.intelligence.temporal_ingestion", "write_temporal_signals"),
    "compute_features": ("app.intelligence.feature_store", "compute_features"),
    "discover_patterns_for_campaign": ("app.intelligence.pattern_engine", "discover_patterns_for_campaign"),
    "discover_cohort_patterns": ("app.intelligence.pattern_engine", "discover_cohort_patterns"),
    "derive_policy": ("app.intelligence.policy_engine", "derive_policy"),
    "score_policy": ("app.intelligence.policy_engine", "score_policy"),
    "generate_recommendations": ("app.intelligence.policy_engine", "generate_recommendations"),
    "aggregate_features": ("app.intelligence.feature_aggregator", "aggregate_features"),
    "build_cohort_profiles": ("app.intelligence.feature_aggregator", "build_cohort_profiles"),
    "describe_campaign_cohort": ("app.intelligence.feature_aggregator", "describe_campaign_cohort"),
    "build_cohort_rows": ("app.intelligence.cohort_feature_aggregator", "build_cohort_rows"),
    "aggregate_feature_profiles": ("app.intelligence.cohort_feature_aggregator", "aggregate_feature_profiles"),
    "discover_learning_cohort_patterns": ("app.intelligence.cohort_pattern_engine", "discover_cohort_patterns"),
    "record_outcome": ("app.intelligence.outcome_tracker", "record_outcome"),
    "compute_reward": ("app.intelligence.outcome_tracker", "compute_reward"),
    "update_policy_weights": ("app.intelligence.policy_update_engine", "update_policy_weights"),
    "update_policy_priority_weights": ("app.intelligence.policy_update_engine", "update_policy_priority_weights"),
    "run_campaign_cycle": ("app.intelligence.intelligence_orchestrator", "run_campaign_cycle"),
    "run_system_cycle": ("app.intelligence.intelligence_orchestrator", "run_system_cycle"),
    "explain_recommendation": ("app.intelligence.llm_explainer", "explain_recommendation"),
    "DigitalTwinState": ("app.intelligence.digital_twin", "DigitalTwinState"),
    "simulate_strategy": ("app.intelligence.digital_twin", "simulate_strategy"),
    "optimize_strategy": ("app.intelligence.digital_twin", "optimize_strategy"),
    "TwinMetricsTracker": ("app.intelligence.digital_twin", "TwinMetricsTracker"),
}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str) -> Any:
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr_name = _EXPORTS[name]
    module = import_module(module_name)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value

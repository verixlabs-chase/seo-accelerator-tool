from app.intelligence.legacy_adapters.diagnostic_adapter import collect_legacy_diagnostics
from app.intelligence.legacy_adapters.executive_summary_adapter import build_legacy_packaging
from app.intelligence.legacy_adapters.scenario_registry_adapter import diagnostics_to_policy_inputs, diagnostics_to_patterns

__all__ = [
    'collect_legacy_diagnostics',
    'build_legacy_packaging',
    'diagnostics_to_policy_inputs',
    'diagnostics_to_patterns',
]

# Unified Runtime Design

## Phase 1 status
The modern intelligence runtime remains canonical for orchestration, simulation, execution, and learning. Legacy strategy-engine capabilities are integrated through adapters rather than a second execution path.

## Adapter layers
- `app/intelligence/legacy_adapters/diagnostic_adapter.py`
- `app/intelligence/legacy_adapters/scenario_registry_adapter.py`
- `app/intelligence/legacy_adapters/executive_summary_adapter.py`

## Runtime flow
```text
modern signals
  -> modern features
  -> modern patterns
  -> legacy diagnostics adapter
  -> merged policy inputs
  -> recommendation persistence
  -> digital twin selection
  -> execution planning
  -> execution
  -> outcomes and learning
  -> legacy-compatible packaging for operator output
```

## Deprecation policy
Legacy strategy-engine modules are marked `DEPRECATED_RUNTIME = True` but remain in place until parity tests show safe removal.

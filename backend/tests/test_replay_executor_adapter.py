from __future__ import annotations

import importlib

from app.governance.replay.schema import ReplayCase
from app.governance.replay.executor_strategy_engine import execute_case as execute_case_strategy


def _minimal_case() -> ReplayCase:
    return ReplayCase.model_validate(
        {
            'case_id': 'case_adapter_smoke',
            'tenant_id': 'tenant_smoke',
            'campaign_id': 'campaign_smoke',
            'input_payload': {
                'window': {
                    'date_from': '2026-02-01T00:00:00Z',
                    'date_to': '2026-02-20T00:00:00Z',
                },
                'raw_signals': {},
                'tier': 'pro',
            },
            'expected_output': {},
            'version_tuple': {
                'engine_version': 'phase2-controlled-scope',
                'threshold_bundle_version': 'v1.0.0',
                'registry_version': 'scenario-registry-v1',
                'signal_schema_version': 'signals-v1',
            },
        }
    )


def test_executor_adapter_import_and_execute_case() -> None:
    module = importlib.import_module('app.governance.replay.executor_adapter')
    execute_case = getattr(module, 'execute_case')

    payload = execute_case(_minimal_case())

    assert isinstance(payload, dict)
    assert payload['campaign_id'] == 'campaign_smoke'


def test_executor_adapter_parity_with_strategy_executor() -> None:
    module = importlib.import_module('app.governance.replay.executor_adapter')
    execute_case_adapter = getattr(module, 'execute_case')

    case = _minimal_case()
    adapter_payload = execute_case_adapter(case)
    strategy_payload = execute_case_strategy(case)

    assert adapter_payload == strategy_payload

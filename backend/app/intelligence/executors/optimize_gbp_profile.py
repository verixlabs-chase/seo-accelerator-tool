from __future__ import annotations

from typing import Any

from app.intelligence.executors.base import BaseExecutor


class OptimizeGbpProfileExecutor(BaseExecutor):
    execution_type = 'optimize_gbp_profile'
    produces_website_mutations = False

    def plan(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.validate(payload)
        return {
            'execution_type': self.execution_type,
            'status': 'planned',
            'actions': ['queue_profile_updates'],
            'artifacts': {'profile_task': 'gbp_opt_v1', 'connector_status': 'pending_real_provider'},
            'metrics_to_measure': self.get_metrics_to_measure(payload),
            'mutations': [],
            'notes': 'GBP optimization remains a non-website execution path and requires a provider-native connector.',
        }

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = self.plan(payload)
        result['status'] = 'completed'
        result['notes'] = 'No website mutation was applied; GBP remains provider-managed.'
        return result

    def get_metrics_to_measure(self, payload: dict[str, Any]) -> list[str]:
        return ['local_health', 'avg_rank']

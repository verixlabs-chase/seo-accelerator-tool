from __future__ import annotations

from typing import Any

from app.intelligence.executors.base import BaseExecutor


class OptimizeGbpProfileExecutor(BaseExecutor):
    execution_type = 'optimize_gbp_profile'

    def plan(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.validate(payload)
        return {
            'execution_type': self.execution_type,
            'status': 'planned',
            'actions': [
                'review_profile_completeness',
                'queue_profile_updates',
                'schedule_local_signal_refresh',
            ],
            'artifacts': {'profile_task': 'gbp_opt_v1'},
            'metrics_to_measure': self.get_metrics_to_measure(payload),
            'notes': 'GBP optimization plan generated deterministically.',
        }

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = self.plan(payload)
        result['status'] = 'completed'
        result['notes'] = 'GBP optimization completed deterministically.'
        return result

    def get_metrics_to_measure(self, payload: dict[str, Any]) -> list[str]:
        return ['local_health', 'avg_rank']

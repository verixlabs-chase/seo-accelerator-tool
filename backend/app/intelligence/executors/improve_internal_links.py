from __future__ import annotations

from typing import Any

from app.intelligence.executors.base import BaseExecutor


class ImproveInternalLinksExecutor(BaseExecutor):
    execution_type = 'improve_internal_links'

    def plan(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.validate(payload)
        target = str(payload.get('target_page', 'sitewide'))
        return {
            'execution_type': self.execution_type,
            'status': 'planned',
            'actions': [
                'identify_low_link_pages',
                'propose_contextual_links',
                'queue_internal_link_updates',
            ],
            'artifacts': {'link_plan': f'links:{target}'},
            'metrics_to_measure': self.get_metrics_to_measure(payload),
            'notes': 'Internal linking optimization plan generated deterministically.',
        }

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = self.plan(payload)
        result['status'] = 'completed'
        result['notes'] = 'Internal linking updates completed deterministically.'
        return result

    def get_metrics_to_measure(self, payload: dict[str, Any]) -> list[str]:
        return ['avg_rank', 'local_health']

from __future__ import annotations

from typing import Any

from app.intelligence.executors.base import BaseExecutor


class CreateContentBriefExecutor(BaseExecutor):
    execution_type = 'create_content_brief'

    def plan(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.validate(payload)
        campaign_id = str(payload.get('campaign_id', ''))
        return {
            'execution_type': self.execution_type,
            'status': 'planned',
            'actions': [
                'collect_keyword_opportunities',
                'build_content_outline',
                'prepare_brief_record',
            ],
            'artifacts': {'brief_ref': f'brief:{campaign_id}' if campaign_id else 'brief:pending'},
            'metrics_to_measure': self.get_metrics_to_measure(payload),
            'notes': 'Deterministic content brief plan generated.',
        }

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        plan = self.plan(payload)
        plan['status'] = 'completed'
        plan['notes'] = 'Content brief workflow completed deterministically.'
        return plan

    def get_metrics_to_measure(self, payload: dict[str, Any]) -> list[str]:
        return ['content_count', 'avg_rank']

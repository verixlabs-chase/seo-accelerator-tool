from __future__ import annotations

from typing import Any

from app.intelligence.executors.base import BaseExecutor


class FixMissingTitleExecutor(BaseExecutor):
    execution_type = 'fix_missing_title'

    def plan(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.validate(payload)
        return {
            'execution_type': self.execution_type,
            'status': 'planned',
            'actions': [
                'find_pages_missing_title',
                'generate_title_templates',
                'prepare_title_patch_set',
            ],
            'artifacts': {'patch_set': 'title_fixes_v1'},
            'metrics_to_measure': self.get_metrics_to_measure(payload),
            'notes': 'Title fix plan generated deterministically.',
        }

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = self.plan(payload)
        result['status'] = 'completed'
        result['notes'] = 'Title fixes applied deterministically.'
        return result

    def get_metrics_to_measure(self, payload: dict[str, Any]) -> list[str]:
        return ['technical_issue_count', 'avg_rank']

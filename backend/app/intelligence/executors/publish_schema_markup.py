from __future__ import annotations

from typing import Any

from app.intelligence.executors.base import BaseExecutor


class PublishSchemaMarkupExecutor(BaseExecutor):
    execution_type = 'publish_schema_markup'

    def plan(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.validate(payload)
        return {
            'execution_type': self.execution_type,
            'status': 'planned',
            'actions': [
                'identify_schema_gaps',
                'generate_schema_payloads',
                'queue_markup_deployment',
            ],
            'artifacts': {'schema_bundle': 'schema_bundle_v1'},
            'metrics_to_measure': self.get_metrics_to_measure(payload),
            'notes': 'Schema markup plan generated deterministically.',
        }

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = self.plan(payload)
        result['status'] = 'completed'
        result['notes'] = 'Schema markup published deterministically.'
        return result

    def get_metrics_to_measure(self, payload: dict[str, Any]) -> list[str]:
        return ['technical_issue_count', 'avg_rank']

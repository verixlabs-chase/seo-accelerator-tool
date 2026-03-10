from __future__ import annotations

from typing import Any

from app.intelligence.executors.base import BaseExecutor
from app.intelligence.executors.mutation_schema import build_mutation, normalize_url_path


class PublishSchemaMarkupExecutor(BaseExecutor):
    execution_type = 'publish_schema_markup'
    produces_website_mutations = True

    def plan(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.validate(payload)
        campaign_name = str(payload.get('campaign_name') or 'Business')
        campaign_domain = str(payload.get('campaign_domain') or '')
        target_url = normalize_url_path(payload.get('target_url') or '/')
        schema_type = str(payload.get('schema_type') or 'Service')
        schema_json = {
            '@context': 'https://schema.org',
            '@type': schema_type,
            'name': campaign_name,
            'url': f'https://{campaign_domain}{target_url}' if campaign_domain else target_url,
            'description': str(payload.get('recommendation_rationale') or f'{campaign_name} structured data block.'),
        }
        mutations = [
            build_mutation(
                action='add_schema_markup',
                target_url=target_url,
                payload={'schema_type': schema_type, 'schema_json': schema_json},
                rollback_hint={'strategy': 'remove_schema_block'},
            )
        ]
        return {
            'execution_type': self.execution_type,
            'status': 'planned',
            'actions': ['add_schema_markup'],
            'artifacts': {'schema_bundle': 'schema_bundle_v2'},
            'metrics_to_measure': self.get_metrics_to_measure(payload),
            'mutations': mutations,
            'notes': 'Schema markup mutations generated for deterministic WordPress delivery.',
        }

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = self.plan(payload)
        result['status'] = 'completed'
        result['notes'] = 'Schema markup mutations generated deterministically.'
        return result

    def get_metrics_to_measure(self, payload: dict[str, Any]) -> list[str]:
        return ['technical_issue_count', 'avg_rank']

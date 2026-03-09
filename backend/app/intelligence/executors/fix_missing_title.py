from __future__ import annotations

from typing import Any

from app.intelligence.executors.base import BaseExecutor
from app.intelligence.executors.mutation_schema import build_mutation, normalize_url_path


class FixMissingTitleExecutor(BaseExecutor):
    execution_type = 'fix_missing_title'
    produces_website_mutations = True

    def plan(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.validate(payload)
        campaign_name = str(payload.get('campaign_name') or 'Campaign')
        campaign_domain = str(payload.get('campaign_domain') or '')
        target_url = normalize_url_path(payload.get('target_url') or '/')
        meta_title = str(payload.get('meta_title') or f'{campaign_name} | {campaign_domain}'.strip(' |'))
        meta_description = str(payload.get('meta_description') or payload.get('recommendation_rationale') or f'Updated SEO metadata for {campaign_name}.')[:160]
        mutations = [
            build_mutation(
                action='update_meta_title',
                target_url=target_url,
                payload={'title': meta_title},
                rollback_hint={'strategy': 'restore_previous_meta_title'},
            ),
            build_mutation(
                action='update_meta_description',
                target_url=target_url,
                payload={'description': meta_description},
                rollback_hint={'strategy': 'restore_previous_meta_description'},
            ),
        ]
        return {
            'execution_type': self.execution_type,
            'status': 'planned',
            'actions': ['update_meta_title', 'update_meta_description'],
            'artifacts': {'patch_set': 'title_and_description_updates'},
            'metrics_to_measure': self.get_metrics_to_measure(payload),
            'mutations': mutations,
            'notes': 'Metadata repair mutations generated for deterministic WordPress delivery.',
        }

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = self.plan(payload)
        result['status'] = 'completed'
        result['notes'] = 'Metadata repair mutations generated deterministically.'
        return result

    def get_metrics_to_measure(self, payload: dict[str, Any]) -> list[str]:
        return ['technical_issue_count', 'avg_rank']

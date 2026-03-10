from __future__ import annotations

from typing import Any

from app.intelligence.executors.base import BaseExecutor
from app.intelligence.executors.mutation_schema import build_mutation, normalize_url_path, slugify


class ImproveInternalLinksExecutor(BaseExecutor):
    execution_type = 'improve_internal_links'
    produces_website_mutations = True

    def plan(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.validate(payload)
        campaign_name = str(payload.get('campaign_name') or 'service page')
        source_url = normalize_url_path(payload.get('source_url') or '/')
        target_url = normalize_url_path(payload.get('target_url') or f'/services/{slugify(campaign_name)}')
        anchor_text = str(payload.get('anchor_text') or campaign_name)
        mutations = [
            build_mutation(
                action='insert_internal_link',
                target_url=source_url,
                source_url=source_url,
                payload={'target_url': target_url, 'anchor_text': anchor_text, 'placement': 'body_first_paragraph'},
                rollback_hint={'strategy': 'remove_inserted_link'},
            ),
            build_mutation(
                action='create_internal_anchor',
                target_url=target_url,
                payload={'anchor_text': anchor_text, 'anchor_slug': slugify(anchor_text)},
                rollback_hint={'strategy': 'remove_anchor'},
            ),
        ]
        return {
            'execution_type': self.execution_type,
            'status': 'planned',
            'actions': ['insert_internal_link', 'create_internal_anchor'],
            'artifacts': {'link_plan': f'links:{target_url}'},
            'metrics_to_measure': self.get_metrics_to_measure(payload),
            'mutations': mutations,
            'notes': 'Internal linking mutations generated for deterministic WordPress delivery.',
        }

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = self.plan(payload)
        result['status'] = 'completed'
        result['notes'] = 'Internal link mutations generated deterministically.'
        return result

    def get_metrics_to_measure(self, payload: dict[str, Any]) -> list[str]:
        return ['avg_rank', 'local_health']

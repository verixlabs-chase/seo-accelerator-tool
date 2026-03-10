from __future__ import annotations

from typing import Any

from app.intelligence.executors.base import BaseExecutor
from app.intelligence.executors.mutation_schema import build_mutation, normalize_url_path, slugify


class CreateContentBriefExecutor(BaseExecutor):
    execution_type = 'create_content_brief'
    produces_website_mutations = True

    def plan(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.validate(payload)
        campaign_name = str(payload.get('campaign_name') or 'Service Page')
        page_title = str(payload.get('content_title') or f'{campaign_name} Service Guide')
        page_slug = str(payload.get('content_slug') or slugify(page_title))
        target_url = normalize_url_path(payload.get('content_target_url') or f'/{page_slug}')
        page_summary = str(payload.get('recommendation_rationale') or f'Publish a structured draft page for {campaign_name}.')
        mutations = [
            build_mutation(
                action='publish_content_page',
                target_url=target_url,
                payload={
                    'title': page_title,
                    'slug': page_slug,
                    'publication_state': 'draft',
                    'content_blocks': [{'type': 'paragraph', 'text': page_summary}],
                    'seo': {
                        'meta_title': str(payload.get('meta_title') or page_title),
                        'meta_description': str(payload.get('meta_description') or page_summary[:150]),
                    },
                },
                rollback_hint={'strategy': 'unpublish_draft_page'},
            )
        ]
        return {
            'execution_type': self.execution_type,
            'status': 'planned',
            'actions': ['publish_content_page'],
            'artifacts': {'brief_ref': f"brief:{payload.get('campaign_id', 'pending')}", 'publication_state': 'draft'},
            'metrics_to_measure': self.get_metrics_to_measure(payload),
            'mutations': mutations,
            'notes': 'Structured draft content page prepared for WordPress mutation delivery.',
        }

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = self.plan(payload)
        result['status'] = 'completed'
        result['notes'] = 'Structured content publication mutations generated deterministically.'
        return result

    def get_metrics_to_measure(self, payload: dict[str, Any]) -> list[str]:
        return ['content_count', 'avg_rank']

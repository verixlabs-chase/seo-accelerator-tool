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
        content_blocks = _content_blocks(payload.get('content_blocks'), fallback=page_summary)
        mutations = [
            build_mutation(
                action='publish_content_page',
                target_url=target_url,
                payload={
                    'title': page_title,
                    'slug': page_slug,
                    'publication_state': 'draft',
                    'content_blocks': content_blocks,
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
            'artifacts': {
                'brief_ref': str(payload.get('content_brief_id') or f"brief:{payload.get('campaign_id', 'pending')}"),
                'content_draft_id': payload.get('content_draft_id'),
                'content_draft_revision': payload.get('content_draft_revision'),
                'content_draft_hash': payload.get('content_draft_hash'),
                'publication_state': 'draft',
            },
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


def _content_blocks(value: Any, *, fallback: str) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return [{'type': 'paragraph', 'text': fallback}]
    normalized: list[dict[str, str]] = []
    for item in value[:24]:
        if not isinstance(item, dict):
            continue
        block_type = str(item.get('type') or '').strip().lower()
        text = str(item.get('text') or '').strip()
        if block_type not in {'heading', 'paragraph'} or not text:
            continue
        normalized.append({'type': block_type, 'text': text[:3000]})
    return normalized or [{'type': 'paragraph', 'text': fallback}]

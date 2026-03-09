from __future__ import annotations

import hashlib
import json
import re
from typing import Any

SUPPORTED_MUTATION_ACTIONS = {
    'update_meta_title',
    'insert_internal_link',
    'add_schema_markup',
    'update_meta_description',
    'create_internal_anchor',
    'publish_content_page',
}


def slugify(value: str) -> str:
    lowered = re.sub(r'[^a-z0-9]+', '-', value.strip().lower())
    compact = lowered.strip('-')
    return compact or 'page'


def normalize_url_path(value: str | None) -> str:
    raw = str(value or '/').strip()
    if not raw:
        return '/'
    if raw.startswith('http://') or raw.startswith('https://'):
        return raw
    return raw if raw.startswith('/') else f'/{raw}'


def build_mutation(*, action: str, target_url: str, payload: dict[str, Any], source_url: str | None = None, rollback_hint: dict[str, Any] | None = None) -> dict[str, Any]:
    if action not in SUPPORTED_MUTATION_ACTIONS:
        raise ValueError(f'Unsupported mutation action: {action}')
    mutation = {
        'action': action,
        'target_url': normalize_url_path(target_url),
        'payload': payload,
    }
    if source_url:
        mutation['source_url'] = normalize_url_path(source_url)
    if rollback_hint:
        mutation['rollback_hint'] = rollback_hint
    canonical = json.dumps(mutation, sort_keys=True, separators=(',', ':'))
    mutation['mutation_id'] = hashlib.sha256(canonical.encode('utf-8')).hexdigest()
    return mutation


def normalize_mutations(mutations: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for mutation in mutations or []:
        if not isinstance(mutation, dict):
            continue
        action = str(mutation.get('action', '') or '')
        payload = mutation.get('payload', {})
        if not isinstance(payload, dict):
            payload = {'value': payload}
        source_url = mutation.get('source_url')
        rollback_hint = mutation.get('rollback_hint')
        normalized.append(
            build_mutation(
                action=action,
                target_url=str(mutation.get('target_url', '/') or '/'),
                payload=payload,
                source_url=str(source_url) if source_url else None,
                rollback_hint=rollback_hint if isinstance(rollback_hint, dict) else None,
            )
        )
    return normalized

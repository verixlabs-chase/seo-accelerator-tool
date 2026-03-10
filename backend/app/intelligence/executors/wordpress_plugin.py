from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime
from typing import Any
from urllib import request
from urllib.error import HTTPError, URLError

from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.intelligence.executors.plugin_telemetry import (
    block_execution_if_plugin_unhealthy,
    detect_plugin_failure,
    track_plugin_health,
    validate_mutation_batch,
    verify_plugin_version,
    verify_rollback_payloads,
)
from app.intelligence.executors.mutation_schema import normalize_mutations
from app.models.campaign import Campaign
from app.models.execution_mutation import ExecutionMutation
from app.models.recommendation_execution import RecommendationExecution
from app.services.provider_client import call_provider
from app.services.provider_credentials_service import ProviderCredentialConfigurationError, resolve_provider_credentials

WORDPRESS_PROVIDER_NAME = 'wordpress_plugin'


class WordPressExecutionError(RuntimeError):
    def __init__(self, message: str, *, reason_code: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


def apply_mutations(db: Session, *, execution: RecommendationExecution, mutations: list[dict[str, Any]]) -> dict[str, Any]:
    normalized = normalize_mutations(mutations)
    if not normalized:
        return {'provider_name': WORDPRESS_PROVIDER_NAME, 'delivery_mode': 'none', 'results': []}
    validate_mutation_batch(normalized)
    site_config = _resolve_site_config(db, execution.campaign_id)
    tenant_id = str(site_config.get('tenant_id', '') or '')
    site_id = str(site_config.get('site_id', execution.campaign_id))
    if tenant_id:
        block_execution_if_plugin_unhealthy(db, tenant_id=tenant_id, site_id=site_id)
    if site_config['mode'] == 'test':
        result = {'provider_name': WORDPRESS_PROVIDER_NAME, 'delivery_mode': 'test_local', 'results': [_local_apply_result(m) for m in normalized]}
        if tenant_id:
            track_plugin_health(db, tenant_id=tenant_id, site_id=site_id, plugin_version='test', healthy=True)
        return result
    payload = {
        'execution_id': execution.id,
        'recommendation_id': execution.recommendation_id,
        'campaign_id': execution.campaign_id,
        'mutations': normalized,
    }
    try:
        response = call_provider(
            WORDPRESS_PROVIDER_NAME,
            'apply_mutations',
            lambda: _post_json(site_config, '/wp-json/lsos/v1/mutations/apply', payload),
            timeout=int(site_config.get('timeout_seconds', 15)),
            retries=3,
        )
        if not verify_plugin_version(response):
            raise WordPressExecutionError('WordPress plugin version is below the minimum supported version.', reason_code='wordpress_version_unsupported')
        normalized_response = _normalize_remote_delivery(response)
        verify_rollback_payloads(normalized_response['results'])
        if tenant_id:
            track_plugin_health(db, tenant_id=tenant_id, site_id=site_id, plugin_version=str(response.get('plugin_version', 'unknown')), healthy=True)
        return normalized_response
    except WordPressExecutionError as exc:
        if tenant_id:
            detect_plugin_failure(db, tenant_id=tenant_id, site_id=site_id, reason_code=exc.reason_code)
        raise


def rollback_mutations(db: Session, *, execution: RecommendationExecution, mutation_rows: list[ExecutionMutation]) -> dict[str, Any]:
    if not mutation_rows:
        return {'provider_name': WORDPRESS_PROVIDER_NAME, 'delivery_mode': 'none', 'results': []}
    site_config = _resolve_site_config(db, execution.campaign_id)
    tenant_id = str(site_config.get('tenant_id', '') or '')
    site_id = str(site_config.get('site_id', execution.campaign_id))
    if site_config['mode'] == 'test':
        result = {'provider_name': WORDPRESS_PROVIDER_NAME, 'delivery_mode': 'test_local', 'results': [_local_rollback_result(row) for row in mutation_rows]}
        if tenant_id:
            track_plugin_health(db, tenant_id=tenant_id, site_id=site_id, plugin_version='test', healthy=True)
        return result
    payload = {
        'execution_id': execution.id,
        'recommendation_id': execution.recommendation_id,
        'campaign_id': execution.campaign_id,
        'mutations': [
            {
                'mutation_id': row.external_mutation_id or row.id,
                'target_url': row.target_url,
                'mutation_type': row.mutation_type,
                'rollback_payload': _loads(row.rollback_payload),
                'before_state': _loads(row.before_state),
            }
            for row in mutation_rows
        ],
    }
    try:
        response = call_provider(
            WORDPRESS_PROVIDER_NAME,
            'rollback_mutations',
            lambda: _post_json(site_config, '/wp-json/lsos/v1/mutations/rollback', payload),
            timeout=int(site_config.get('timeout_seconds', 15)),
            retries=3,
        )
        if not verify_plugin_version(response):
            raise WordPressExecutionError('WordPress plugin version is below the minimum supported version.', reason_code='wordpress_version_unsupported')
        normalized = _normalize_remote_delivery(response)
        verify_rollback_payloads(normalized['results'])
        if tenant_id:
            track_plugin_health(db, tenant_id=tenant_id, site_id=site_id, plugin_version=str(response.get('plugin_version', 'unknown')), healthy=True)
        return normalized
    except WordPressExecutionError as exc:
        if tenant_id:
            detect_plugin_failure(db, tenant_id=tenant_id, site_id=site_id, reason_code=exc.reason_code)
        raise


def _resolve_site_config(db: Session, campaign_id: str) -> dict[str, Any]:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None:
        raise WordPressExecutionError('Campaign not found for execution transport.', reason_code='campaign_not_found')
    settings = get_settings()
    if settings.app_env.lower() == 'test':
        return {'mode': 'test', 'base_url': f'https://{campaign.domain}', 'timeout_seconds': 1, 'tenant_id': campaign.tenant_id, 'site_id': campaign.domain}
    if not campaign.organization_id:
        raise WordPressExecutionError('Organization-scoped WordPress credential is required for live mutation delivery.', reason_code='organization_missing')
    try:
        credentials = resolve_provider_credentials(db, campaign.organization_id, WORDPRESS_PROVIDER_NAME)
    except ProviderCredentialConfigurationError as exc:
        raise WordPressExecutionError(str(exc), reason_code=exc.reason_code) from exc
    if not credentials:
        raise WordPressExecutionError('WordPress plugin credentials are not configured for this organization.', reason_code='wordpress_credentials_missing')
    base_url = str(credentials.get('base_url') or credentials.get('site_url') or '').rstrip('/')
    token = str(credentials.get('plugin_token') or credentials.get('bearer_token') or '').strip()
    shared_secret = str(credentials.get('shared_secret') or '').strip()
    timeout_seconds = int(credentials.get('timeout_seconds') or 15)
    if not base_url or not token or not shared_secret:
        raise WordPressExecutionError('WordPress plugin credentials must include base_url, plugin_token, and shared_secret.', reason_code='wordpress_credentials_incomplete')
    return {'mode': 'live', 'base_url': base_url, 'token': token, 'shared_secret': shared_secret, 'timeout_seconds': timeout_seconds, 'plugin_version': str(credentials.get('plugin_version') or ''), 'tenant_id': campaign.tenant_id, 'site_id': campaign.domain}


def _post_json(site_config: dict[str, Any], path: str, payload: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(payload, sort_keys=True).encode('utf-8')
    timestamp = datetime.now(UTC).isoformat()
    signature = hmac.new(site_config['shared_secret'].encode('utf-8'), msg=timestamp.encode('utf-8') + b'.' + body, digestmod=hashlib.sha256).hexdigest()
    req = request.Request(
        url=f"{site_config['base_url']}{path}",
        data=body,
        method='POST',
        headers={
            'Authorization': f"Bearer {site_config['token']}",
            'Content-Type': 'application/json',
            'X-LSOS-Timestamp': timestamp,
            'X-LSOS-Signature': signature,
        },
    )
    try:
        with request.urlopen(req, timeout=float(site_config['timeout_seconds'])) as response:
            raw = response.read().decode('utf-8')
    except HTTPError as exc:  # pragma: no cover
        raise WordPressExecutionError(f'WordPress plugin rejected mutation request: HTTP {exc.code}', reason_code='wordpress_http_error') from exc
    except URLError as exc:  # pragma: no cover
        raise WordPressExecutionError('WordPress plugin endpoint is unreachable.', reason_code='wordpress_unreachable') from exc
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:  # pragma: no cover
        raise WordPressExecutionError('WordPress plugin returned invalid JSON.', reason_code='wordpress_invalid_response') from exc
    if not isinstance(parsed, dict):
        raise WordPressExecutionError('WordPress plugin returned an invalid response body.', reason_code='wordpress_invalid_response')
    return parsed


def _normalize_remote_delivery(response: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(response, dict):
        raise WordPressExecutionError('WordPress plugin response is invalid.', reason_code='wordpress_invalid_response')
    results = response.get('results', [])
    normalized_results: list[dict[str, Any]] = []
    for item in results if isinstance(results, list) else []:
        if not isinstance(item, dict):
            continue
        normalized_results.append(
            {
                'mutation_id': str(item.get('mutation_id') or item.get('id') or ''),
                'status': str(item.get('status', 'applied') or 'applied'),
                'mutation_type': str(item.get('mutation_type') or item.get('action') or ''),
                'target_url': str(item.get('target_url', '/') or '/'),
                'before_state': item.get('before_state') if isinstance(item.get('before_state'), dict) else {},
                'after_state': item.get('after_state') if isinstance(item.get('after_state'), dict) else {},
                'rollback_payload': item.get('rollback_payload') if isinstance(item.get('rollback_payload'), dict) else {},
            }
        )
    return {'provider_name': WORDPRESS_PROVIDER_NAME, 'delivery_mode': str(response.get('delivery_mode', 'wordpress_plugin') or 'wordpress_plugin'), 'results': normalized_results}


def _local_apply_result(mutation: dict[str, Any]) -> dict[str, Any]:
    before_state = {'target_url': mutation['target_url'], 'action': mutation['action'], 'snapshot_state': 'before', 'payload_fingerprint': mutation['mutation_id']}
    after_state = {'target_url': mutation['target_url'], 'action': mutation['action'], 'snapshot_state': 'after', 'payload': mutation['payload']}
    return {
        'mutation_id': mutation['mutation_id'],
        'status': 'applied',
        'mutation_type': mutation['action'],
        'target_url': mutation['target_url'],
        'before_state': before_state,
        'after_state': after_state,
        'rollback_payload': {'target_url': mutation['target_url'], 'restore_snapshot': before_state},
    }


def _local_rollback_result(row: ExecutionMutation) -> dict[str, Any]:
    return {
        'mutation_id': row.external_mutation_id or row.id,
        'status': 'rolled_back',
        'mutation_type': row.mutation_type,
        'target_url': row.target_url,
        'before_state': _loads(row.before_state),
        'after_state': _loads(row.after_state),
        'rollback_payload': _loads(row.rollback_payload),
    }


def _loads(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}

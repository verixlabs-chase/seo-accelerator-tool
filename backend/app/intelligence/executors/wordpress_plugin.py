from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import UTC, datetime
from typing import Any
from urllib import request
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse

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
from app.services.provider_client import ProviderCallError, call_provider
from app.services.provider_credentials_service import ProviderCredentialConfigurationError, resolve_provider_credentials
from app.services.wordpress_connection_service import (
    get_site_connection,
    get_site_credentials,
)
from app.services.wordpress_public_verification_service import verify_public_mutation_delivery

WORDPRESS_PROVIDER_NAME = 'wordpress_plugin'
WORDPRESS_CONNECTOR_USER_AGENT = 'InsightOS-WordPress-Connector/1.5 (+https://insightos.verixlabs.com)'
MAX_CONTENT_INVENTORY_ITEMS = 500
CONTENT_INVENTORY_PAGE_SIZE = 50


class WordPressExecutionError(RuntimeError):
    def __init__(self, message: str, *, reason_code: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


def check_connection(db: Session, *, campaign_id: str) -> dict[str, Any]:
    """Run one authenticated, read-only handshake before enabling live mutations."""

    site_config = _resolve_site_config(db, campaign_id)
    tenant_id = str(site_config.get('tenant_id', '') or '')
    site_id = str(site_config.get('site_id', campaign_id))
    if site_config['mode'] == 'test':
        return {
            'connected': True,
            'mode': 'test',
            'plugin_version': 'test',
            'wordpress_version': 'test',
            'php_version': 'test',
            'site_url': site_config['base_url'],
            'supported_actions': [],
            'checked_at': datetime.now(UTC).isoformat(),
        }
    try:
        response = call_provider(
            WORDPRESS_PROVIDER_NAME,
            'connection_health',
            lambda: _post_json(
                site_config,
                '/wp-json/lsos/v1/health',
                {'campaign_id': campaign_id, 'check': 'connection_health'},
            ),
            timeout=int(site_config.get('timeout_seconds', 15)),
            retries=1,
        )
        if not verify_plugin_version(response):
            raise WordPressExecutionError(
                'Update the InsightOS WordPress plugin before enabling website changes.',
                reason_code='wordpress_version_unsupported',
            )
        response_site_url = str(response.get('site_url') or response.get('home_url') or '').strip()
        expected_host = _normalized_host(site_config['base_url'])
        actual_host = _normalized_host(response_site_url)
        if not response_site_url or actual_host != expected_host:
            raise WordPressExecutionError(
                'The plugin responded from a different website than this location.',
                reason_code='wordpress_site_mismatch',
            )
        permissions = response.get('permissions') if isinstance(response.get('permissions'), dict) else {}
        if not all(bool(permissions.get(key)) for key in ('mutations', 'rollback', 'health_check', 'content_inventory', 'change_preview')):
            raise WordPressExecutionError(
                'The plugin is connected but does not have all required safe-change permissions.',
                reason_code='wordpress_permissions_incomplete',
            )
        plugin_version = str(response.get('plugin_version') or '')
        if tenant_id:
            track_plugin_health(
                db,
                tenant_id=tenant_id,
                site_id=site_id,
                plugin_version=plugin_version,
                healthy=True,
            )
        return {
            'connected': True,
            'mode': 'live',
            'plugin_version': plugin_version,
            'wordpress_version': str(response.get('wordpress_version') or ''),
            'php_version': str(response.get('php_version') or ''),
            'site_url': response_site_url,
            'supported_actions': [
                str(item)
                for item in (response.get('supported_actions') or [])
                if isinstance(item, str)
            ],
            'checked_at': datetime.now(UTC).isoformat(),
        }
    except WordPressExecutionError as exc:
        if tenant_id:
            detect_plugin_failure(
                db,
                tenant_id=tenant_id,
                site_id=site_id,
                reason_code=exc.reason_code,
            )
        raise
    except ProviderCallError as exc:
        translated = _translate_provider_call_error(exc)
        if tenant_id:
            detect_plugin_failure(
                db,
                tenant_id=tenant_id,
                site_id=site_id,
                reason_code=translated.reason_code,
            )
        raise translated from exc


def fetch_content_inventory(db: Session, *, campaign_id: str) -> dict[str, Any]:
    """Read a bounded, metadata-only snapshot of WordPress content."""

    site_config = _resolve_site_config(db, campaign_id)
    tenant_id = str(site_config.get('tenant_id', '') or '')
    site_id = str(site_config.get('site_id', campaign_id))
    if site_config['mode'] == 'test':
        return {
            'mode': 'test',
            'plugin_version': 'test',
            'wordpress_version': 'test',
            'php_version': 'test',
            'site_url': site_config['base_url'],
            'seo_plugins': [],
            'total_items': 0,
            'truncated': False,
            'items': [],
        }

    items: list[dict[str, Any]] = []
    metadata: dict[str, Any] = {}
    page = 1
    max_pages = MAX_CONTENT_INVENTORY_ITEMS // CONTENT_INVENTORY_PAGE_SIZE
    try:
        while page <= max_pages:
            response = call_provider(
                WORDPRESS_PROVIDER_NAME,
                'content_inventory',
                lambda current_page=page: _post_json(
                    site_config,
                    '/wp-json/lsos/v1/content/inventory',
                    {'campaign_id': campaign_id, 'page': current_page, 'per_page': CONTENT_INVENTORY_PAGE_SIZE},
                ),
                timeout=int(site_config.get('timeout_seconds', 15)),
                retries=1,
            )
            _validate_inventory_response(response, expected_base_url=site_config['base_url'])
            if not metadata:
                metadata = {
                    'plugin_version': str(response.get('plugin_version') or ''),
                    'wordpress_version': str(response.get('wordpress_version') or ''),
                    'php_version': str(response.get('php_version') or ''),
                    'site_url': str(response.get('site_url') or ''),
                    'seo_plugins': [
                        item for item in (response.get('seo_plugins') or []) if isinstance(item, dict)
                    ][:10],
                    'total_items': max(0, int(response.get('total_items') or 0)),
                }
            for raw_item in response.get('items') or []:
                if not isinstance(raw_item, dict):
                    continue
                items.append(_normalize_inventory_item(raw_item, site_config['base_url']))
                if len(items) >= MAX_CONTENT_INVENTORY_ITEMS:
                    break
            total_pages = max(1, int(response.get('total_pages') or 1))
            if len(items) >= MAX_CONTENT_INVENTORY_ITEMS or page >= total_pages:
                break
            page += 1
        plugin_version = str(metadata.get('plugin_version') or '')
        if tenant_id:
            track_plugin_health(
                db,
                tenant_id=tenant_id,
                site_id=site_id,
                plugin_version=plugin_version,
                healthy=True,
            )
        total_items = int(metadata.get('total_items') or len(items))
        return {
            'mode': 'live',
            **metadata,
            'total_items': total_items,
            'truncated': total_items > len(items),
            'items': items,
        }
    except WordPressExecutionError as exc:
        if tenant_id:
            detect_plugin_failure(db, tenant_id=tenant_id, site_id=site_id, reason_code=exc.reason_code)
        raise
    except ProviderCallError as exc:
        translated = _translate_provider_call_error(exc)
        if tenant_id:
            detect_plugin_failure(db, tenant_id=tenant_id, site_id=site_id, reason_code=translated.reason_code)
        raise translated from exc


def disconnect_connection(db: Session, *, campaign_id: str) -> dict[str, Any]:
    """Ask the authenticated plugin to erase its site credentials."""

    site_config = _resolve_site_config(db, campaign_id)
    if site_config["mode"] == "test":
        return {"disconnected": True, "mode": "test"}
    try:
        response = call_provider(
            WORDPRESS_PROVIDER_NAME,
            "disconnect",
            lambda: _post_json(
                site_config,
                "/wp-json/lsos/v1/connection/disconnect",
                {"campaign_id": campaign_id, "action": "disconnect"},
            ),
            timeout=int(site_config.get("timeout_seconds", 15)),
            retries=1,
        )
    except ProviderCallError as exc:
        raise _translate_provider_call_error(exc) from exc
    if not bool(response.get("disconnected")):
        raise WordPressExecutionError(
            "WordPress did not confirm the disconnect. Open the plugin settings and disconnect it there.",
            reason_code="wordpress_disconnect_not_confirmed",
        )
    return {"disconnected": True, "mode": "live"}


def preview_mutations(db: Session, *, execution: RecommendationExecution, mutations: list[dict[str, Any]]) -> dict[str, Any]:
    """Read exact current values and proposed values without changing WordPress."""

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
        return {
            'provider_name': WORDPRESS_PROVIDER_NAME,
            'delivery_mode': 'test_local',
            'results': [_local_preview_result(item) for item in normalized],
        }
    payload = {
        'execution_id': execution.id,
        'recommendation_id': execution.recommendation_id,
        'campaign_id': execution.campaign_id,
        'mutations': normalized,
    }
    try:
        response = call_provider(
            WORDPRESS_PROVIDER_NAME,
            'preview_mutations',
            lambda: _post_json(site_config, '/wp-json/lsos/v1/mutations/preview', payload),
            timeout=int(site_config.get('timeout_seconds', 15)),
            retries=1,
        )
        if not verify_plugin_version(response):
            raise WordPressExecutionError(
                'Update the InsightOS WordPress plugin before previewing website changes.',
                reason_code='wordpress_version_unsupported',
            )
        if _normalized_host(str(response.get('site_url') or '')) != _normalized_host(site_config['base_url']):
            raise WordPressExecutionError(
                'The change preview came from a different website than this business.',
                reason_code='wordpress_site_mismatch',
            )
        normalized_response = _normalize_remote_preview(response)
        if tenant_id:
            track_plugin_health(
                db,
                tenant_id=tenant_id,
                site_id=site_id,
                plugin_version=str(response.get('plugin_version', 'unknown')),
                healthy=True,
                commit=False,
            )
        return normalized_response
    except WordPressExecutionError as exc:
        if tenant_id:
            detect_plugin_failure(
                db,
                tenant_id=tenant_id,
                site_id=site_id,
                reason_code=exc.reason_code,
                commit=False,
            )
        raise
    except ProviderCallError as exc:
        translated = _translate_provider_call_error(exc)
        if tenant_id:
            detect_plugin_failure(
                db,
                tenant_id=tenant_id,
                site_id=site_id,
                reason_code=translated.reason_code,
                commit=False,
            )
        raise translated from exc


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
        results = [_local_apply_result(m) for m in normalized]
        result = {
            'provider_name': WORDPRESS_PROVIDER_NAME,
            'delivery_mode': 'test_local',
            'results': results,
            'public_verification': {
                'passed': True,
                'verified_at': datetime.now(UTC).isoformat(),
                'pages_checked': len({str(item.get('target_url') or '/') for item in normalized}),
                'checks_total': len(normalized),
                'checks_passed': len(normalized),
                'checks_failed': 0,
                'rollback_available': True,
                'results': [
                    {
                        'mutation_id': item['mutation_id'],
                        'mutation_type': item['action'],
                        'target_url': str(item.get('source_url') or item.get('target_url') or '/'),
                        'status': 'simulated',
                        'passed': True,
                        'message': 'Public verification is simulated in the test environment.',
                    }
                    for item in normalized
                ],
            },
        }
        if tenant_id:
            track_plugin_health(
                db,
                tenant_id=tenant_id,
                site_id=site_id,
                plugin_version='test',
                healthy=True,
                commit=False,
            )
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
        normalized_response['public_verification'] = verify_public_mutation_delivery(
            base_url=site_config['base_url'],
            mutations=normalized,
            results=normalized_response['results'],
            timeout_seconds=int(site_config.get('timeout_seconds', 15)),
        )
        if tenant_id:
            track_plugin_health(
                db,
                tenant_id=tenant_id,
                site_id=site_id,
                plugin_version=str(response.get('plugin_version', 'unknown')),
                healthy=True,
                commit=False,
            )
        return normalized_response
    except WordPressExecutionError as exc:
        if tenant_id:
            detect_plugin_failure(
                db,
                tenant_id=tenant_id,
                site_id=site_id,
                reason_code=exc.reason_code,
                commit=False,
            )
        raise
    except ProviderCallError as exc:
        translated = _translate_provider_call_error(exc)
        if tenant_id:
            detect_plugin_failure(
                db,
                tenant_id=tenant_id,
                site_id=site_id,
                reason_code=translated.reason_code,
                commit=False,
            )
        raise translated from exc


def rollback_mutations(db: Session, *, execution: RecommendationExecution, mutation_rows: list[ExecutionMutation]) -> dict[str, Any]:
    if not mutation_rows:
        return {'provider_name': WORDPRESS_PROVIDER_NAME, 'delivery_mode': 'none', 'results': []}
    site_config = _resolve_site_config(db, execution.campaign_id)
    tenant_id = str(site_config.get('tenant_id', '') or '')
    site_id = str(site_config.get('site_id', execution.campaign_id))
    if site_config['mode'] == 'test':
        result = {'provider_name': WORDPRESS_PROVIDER_NAME, 'delivery_mode': 'test_local', 'results': [_local_rollback_result(row) for row in mutation_rows]}
        if tenant_id:
            track_plugin_health(
                db,
                tenant_id=tenant_id,
                site_id=site_id,
                plugin_version='test',
                healthy=True,
                commit=False,
            )
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
            track_plugin_health(
                db,
                tenant_id=tenant_id,
                site_id=site_id,
                plugin_version=str(response.get('plugin_version', 'unknown')),
                healthy=True,
                commit=False,
            )
        return normalized
    except WordPressExecutionError as exc:
        if tenant_id:
            detect_plugin_failure(
                db,
                tenant_id=tenant_id,
                site_id=site_id,
                reason_code=exc.reason_code,
                commit=False,
            )
        raise
    except ProviderCallError as exc:
        translated = _translate_provider_call_error(exc)
        if tenant_id:
            detect_plugin_failure(
                db,
                tenant_id=tenant_id,
                site_id=site_id,
                reason_code=translated.reason_code,
                commit=False,
            )
        raise translated from exc


def _resolve_site_config(db: Session, campaign_id: str) -> dict[str, Any]:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None:
        raise WordPressExecutionError('Campaign not found for execution transport.', reason_code='campaign_not_found')
    settings = get_settings()
    if settings.app_env.lower() == 'test':
        return {'mode': 'test', 'base_url': f'https://{campaign.domain}', 'timeout_seconds': 1, 'tenant_id': campaign.tenant_id, 'site_id': campaign.domain}
    if not campaign.organization_id:
        raise WordPressExecutionError('Organization-scoped WordPress credential is required for live mutation delivery.', reason_code='organization_missing')
    connection = get_site_connection(db, campaign_id=campaign.id)
    site_credentials = get_site_credentials(db, campaign_id=campaign.id)
    if site_credentials:
        return _live_site_config(campaign, site_credentials)
    if connection is not None and connection.status == 'disconnected':
        raise WordPressExecutionError(
            'This WordPress site is disconnected. Create a new pairing code to reconnect it.',
            reason_code='wordpress_site_disconnected',
        )
    try:
        credentials = resolve_provider_credentials(db, campaign.organization_id, WORDPRESS_PROVIDER_NAME)
    except ProviderCredentialConfigurationError as exc:
        raise WordPressExecutionError(str(exc), reason_code=exc.reason_code) from exc
    if not credentials:
        raise WordPressExecutionError('WordPress plugin credentials are not configured for this organization.', reason_code='wordpress_credentials_missing')
    return _live_site_config(campaign, credentials)


def _live_site_config(campaign: Campaign, credentials: dict[str, Any]) -> dict[str, Any]:
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
    nonce = uuid.uuid4().hex
    signature_payload = timestamp.encode('utf-8') + b'.' + nonce.encode('ascii') + b'.' + body
    signature = hmac.new(site_config['shared_secret'].encode('utf-8'), msg=signature_payload, digestmod=hashlib.sha256).hexdigest()
    req = request.Request(
        url=f"{site_config['base_url']}{path}",
        data=body,
        method='POST',
        headers={
            'Accept': 'application/json',
            'Authorization': f"Bearer {site_config['token']}",
            'Content-Type': 'application/json',
            'User-Agent': WORDPRESS_CONNECTOR_USER_AGENT,
            'X-LSOS-Timestamp': timestamp,
            'X-LSOS-Nonce': nonce,
            'X-LSOS-Signature': signature,
        },
    )
    try:
        with request.urlopen(req, timeout=float(site_config['timeout_seconds'])) as response:
            raw = response.read().decode('utf-8')
    except HTTPError as exc:  # pragma: no cover
        try:
            error_payload = json.loads(exc.read().decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError):
            error_payload = {}
        message = str(error_payload.get('message') or f'WordPress rejected the request with HTTP {exc.code}.')
        reason_code = str(error_payload.get('reason_code') or error_payload.get('code') or 'wordpress_http_error')
        raise WordPressExecutionError(message, reason_code=reason_code[:80]) from exc
    except URLError as exc:  # pragma: no cover
        raise WordPressExecutionError('WordPress plugin endpoint is unreachable.', reason_code='wordpress_unreachable') from exc
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:  # pragma: no cover
        raise WordPressExecutionError('WordPress plugin returned invalid JSON.', reason_code='wordpress_invalid_response') from exc
    if not isinstance(parsed, dict):
        raise WordPressExecutionError('WordPress plugin returned an invalid response body.', reason_code='wordpress_invalid_response')
    return parsed


def _normalized_host(value: str) -> str:
    raw = str(value or '').strip()
    parsed = urlparse(raw if '://' in raw else f'https://{raw}')
    host = str(parsed.hostname or '').lower()
    return host[4:] if host.startswith('www.') else host


def _validate_inventory_response(response: dict[str, Any], *, expected_base_url: str) -> None:
    if not verify_plugin_version(response):
        raise WordPressExecutionError(
            'Update the InsightOS WordPress plugin before syncing website pages.',
            reason_code='wordpress_version_unsupported',
        )
    if _normalized_host(str(response.get('site_url') or '')) != _normalized_host(expected_base_url):
        raise WordPressExecutionError(
            'The page inventory came from a different website than this business.',
            reason_code='wordpress_site_mismatch',
        )
    if not isinstance(response.get('items'), list):
        raise WordPressExecutionError(
            'WordPress returned an invalid page inventory.',
            reason_code='wordpress_inventory_invalid',
        )


def _normalize_inventory_item(item: dict[str, Any], expected_base_url: str) -> dict[str, Any]:
    try:
        wp_post_id = int(item.get('wp_post_id') or 0)
        word_count = max(0, int(item.get('word_count') or 0))
    except (TypeError, ValueError) as exc:
        raise WordPressExecutionError(
            'WordPress returned an invalid page record.',
            reason_code='wordpress_inventory_invalid',
        ) from exc
    url = str(item.get('url') or '').strip()
    content_hash = str(item.get('content_hash') or '').lower()
    revision_id = str(item.get('revision_id') or '').strip()
    if (
        wp_post_id <= 0
        or not url
        or _normalized_host(url) != _normalized_host(expected_base_url)
        or len(content_hash) != 64
        or any(character not in '0123456789abcdef' for character in content_hash)
        or not revision_id
    ):
        raise WordPressExecutionError(
            'WordPress returned a page record that could not be verified.',
            reason_code='wordpress_inventory_invalid',
        )
    return {
        'wp_post_id': wp_post_id,
        'post_type': str(item.get('post_type') or 'post')[:80],
        'publication_status': str(item.get('publication_status') or 'unknown')[:24],
        'slug': str(item.get('slug') or '')[:320],
        'url': url,
        'title': str(item.get('title') or ''),
        'meta_title': str(item.get('meta_title') or '') or None,
        'meta_description': str(item.get('meta_description') or '') or None,
        'canonical_url': str(item.get('canonical_url') or '') or None,
        'headings': [value for value in (item.get('headings') or []) if isinstance(value, dict)][:40],
        'internal_links': [str(value) for value in (item.get('internal_links') or []) if value][:100],
        'schema_types': [str(value) for value in (item.get('schema_types') or []) if value][:20],
        'schema_present': bool(item.get('schema_present')),
        'word_count': word_count,
        'revision_id': revision_id[:120],
        'content_hash': content_hash,
        'modified_at': str(item.get('modified_at') or '') or None,
    }


def _translate_provider_call_error(exc: ProviderCallError) -> WordPressExecutionError:
    cause = exc.__cause__
    if isinstance(cause, WordPressExecutionError):
        return WordPressExecutionError(str(cause), reason_code=cause.reason_code)
    return WordPressExecutionError(
        'The WordPress plugin could not be reached. Check the site URL, plugin, and firewall, then try again.',
        reason_code='wordpress_unreachable',
    )


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


def _normalize_remote_preview(response: dict[str, Any]) -> dict[str, Any]:
    results = response.get('results')
    if not isinstance(results, list) or not results:
        raise WordPressExecutionError(
            'WordPress did not return a usable change preview.',
            reason_code='wordpress_preview_invalid',
        )
    normalized_results: list[dict[str, Any]] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        expected_version = item.get('expected_version')
        if not isinstance(expected_version, dict) or not expected_version.get('revision_id') or not expected_version.get('content_hash'):
            raise WordPressExecutionError(
                'WordPress did not return a verifiable page version for every proposed change.',
                reason_code='wordpress_preview_version_missing',
            )
        normalized_results.append(
            {
                'mutation_id': str(item.get('mutation_id') or ''),
                'mutation_type': str(item.get('mutation_type') or item.get('action') or ''),
                'target_url': str(item.get('target_url') or '/'),
                'before': item.get('before') if isinstance(item.get('before'), dict) else {},
                'after': item.get('after') if isinstance(item.get('after'), dict) else {},
                'expected_version': {
                    'revision_id': str(expected_version.get('revision_id') or ''),
                    'content_hash': str(expected_version.get('content_hash') or ''),
                },
                'validation_checks': [
                    check for check in (item.get('validation_checks') or []) if isinstance(check, dict)
                ],
                'conflicts': [
                    conflict for conflict in (item.get('conflicts') or []) if isinstance(conflict, dict)
                ],
                'rollback_plan': item.get('rollback_plan') if isinstance(item.get('rollback_plan'), dict) else {},
            }
        )
    if not normalized_results:
        raise WordPressExecutionError(
            'WordPress did not return a usable change preview.',
            reason_code='wordpress_preview_invalid',
        )
    return {
        'provider_name': WORDPRESS_PROVIDER_NAME,
        'delivery_mode': str(response.get('delivery_mode') or 'wordpress_plugin'),
        'results': normalized_results,
    }


def _local_preview_result(mutation: dict[str, Any]) -> dict[str, Any]:
    target_url = str(mutation.get('source_url') or mutation.get('target_url') or '/')
    version_seed = f'test-wordpress:{target_url}'
    payload = mutation.get('payload') if isinstance(mutation.get('payload'), dict) else {}
    return {
        'mutation_id': mutation['mutation_id'],
        'mutation_type': mutation['action'],
        'target_url': target_url,
        'before': {'current_value': None, 'page': target_url},
        'after': {'proposed_value': payload, 'page': target_url},
        'expected_version': {
            'revision_id': f"test:{hashlib.sha256(target_url.encode('utf-8')).hexdigest()[:16]}",
            'content_hash': hashlib.sha256(version_seed.encode('utf-8')).hexdigest(),
        },
        'validation_checks': [
            {'code': 'target_ready', 'passed': True, 'message': 'The page is available for this change.'},
            {'code': 'value_checked', 'passed': True, 'message': 'The current and proposed values were compared.'},
        ],
        'conflicts': [],
        'rollback_plan': {'available': True, 'summary': 'Restore the saved value from before this change.'},
    }


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

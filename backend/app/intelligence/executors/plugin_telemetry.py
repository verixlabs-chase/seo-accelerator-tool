from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime
import re
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.provider_health import ProviderHealthState
from app.services.provider_telemetry_service import ProviderTelemetryService

WORDPRESS_PROVIDER_NAME = 'wordpress_plugin'
WORDPRESS_CAPABILITY = 'mutation_execution'
MINIMUM_PLUGIN_VERSION = '1.0.0'
MAX_MUTATIONS_PER_PAGE = 5
PROTECTED_URL_PREFIXES = ('/wp-admin', '/wp-login.php', '/checkout', '/cart')
_SELECTOR_PATTERN = re.compile(r'^[A-Za-z0-9#._:\-\[\]="\'\s>+~(),]+$')


class PluginTelemetryError(RuntimeError):
    pass


def track_plugin_health(
    db: Session,
    *,
    tenant_id: str,
    site_id: str,
    plugin_version: str | None,
    healthy: bool,
    error_code: str | None = None,
) -> None:
    telemetry = ProviderTelemetryService(db)
    telemetry.upsert_health_state(
        tenant_id=tenant_id,
        provider_name=WORDPRESS_PROVIDER_NAME,
        capability=f'{WORDPRESS_CAPABILITY}:{site_id}',
        breaker_state='closed' if healthy else 'open',
        consecutive_failures=0 if healthy else 1,
        provider_version=plugin_version,
        last_error_code=error_code,
        last_error_at=None if healthy else datetime.now(UTC),
        last_success_at=datetime.now(UTC) if healthy else None,
        environment=get_settings().app_env.lower(),
    )


def verify_plugin_version(site_config: dict[str, Any], minimum_version: str = MINIMUM_PLUGIN_VERSION) -> bool:
    version = str(site_config.get('plugin_version') or minimum_version)
    return _version_tuple(version) >= _version_tuple(minimum_version)


def detect_plugin_failure(db: Session, *, tenant_id: str, site_id: str, reason_code: str, plugin_version: str | None = None) -> None:
    track_plugin_health(
        db,
        tenant_id=tenant_id,
        site_id=site_id,
        plugin_version=plugin_version,
        healthy=False,
        error_code=reason_code,
    )


def block_execution_if_plugin_unhealthy(db: Session, *, tenant_id: str, site_id: str) -> None:
    row = (
        db.query(ProviderHealthState)
        .filter(
            ProviderHealthState.tenant_id == tenant_id,
            ProviderHealthState.provider_name == WORDPRESS_PROVIDER_NAME,
            ProviderHealthState.capability == f'{WORDPRESS_CAPABILITY}:{site_id}',
        )
        .order_by(ProviderHealthState.updated_at.desc())
        .first()
    )
    if row is None:
        return
    if str(row.breaker_state).lower() == 'open':
        raise PluginTelemetryError(f'WordPress plugin health is open for site {site_id}.')


def validate_mutation_batch(mutations: list[dict[str, Any]]) -> None:
    per_page_counts: Counter[str] = Counter()
    selector_errors: defaultdict[str, list[str]] = defaultdict(list)
    for mutation in mutations:
        target_url = str(mutation.get('target_url', '/') or '/')
        if any(target_url.startswith(prefix) for prefix in PROTECTED_URL_PREFIXES):
            raise PluginTelemetryError(f'Mutation target is protected: {target_url}')
        per_page_counts[target_url] += 1
        if per_page_counts[target_url] > MAX_MUTATIONS_PER_PAGE:
            raise PluginTelemetryError(f'Max mutations per page exceeded for {target_url}')
        payload = mutation.get('payload', {})
        if not isinstance(payload, dict):
            continue
        for key in ('selector', 'container_selector', 'target_selector'):
            if key not in payload:
                continue
            selector = str(payload.get(key) or '')
            if selector and not _SELECTOR_PATTERN.match(selector):
                selector_errors[target_url].append(selector)
    if selector_errors:
        first_target, values = next(iter(selector_errors.items()))
        raise PluginTelemetryError(f'Invalid DOM selector for {first_target}: {values[0]}')


def verify_rollback_payloads(results: list[dict[str, Any]]) -> None:
    for item in results:
        rollback_payload = item.get('rollback_payload')
        before_state = item.get('before_state')
        after_state = item.get('after_state')
        if not isinstance(rollback_payload, dict) or not rollback_payload:
            raise PluginTelemetryError('Mutation response is missing rollback payload.')
        if not isinstance(before_state, dict) or not isinstance(after_state, dict):
            raise PluginTelemetryError('Mutation response is missing before/after state snapshots.')


def _version_tuple(value: str) -> tuple[int, ...]:
    parts = []
    for token in str(value).split('.'):
        try:
            parts.append(int(token))
        except ValueError:
            parts.append(0)
    return tuple(parts or [0])

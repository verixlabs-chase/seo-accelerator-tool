from __future__ import annotations

import json
import ipaddress
import socket
from datetime import UTC, datetime
from hashlib import sha256
from collections.abc import Callable
from urllib.parse import urlsplit

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.crypto import CredentialCryptoError, decrypt_payload, encrypt_payload
from app.models.governed_ai_provider_connection import GovernedAIProviderConnection
from app.models.organization import Organization
from app.services.commercial_plan_service import (
    FEATURE_PRIVATE_AI_PROVIDER,
    require_commercial_feature,
)
from app.services.governed_ai_provider import (
    GovernedAIProviderError,
    validate_openai_compatible_endpoint,
)


_CAPABILITIES = ("explain", "question_answer", "draft", "keyword_filter", "baseline")


class GovernedAIProviderConnectionError(RuntimeError):
    def __init__(self, message: str, *, reason_code: str, status_code: int) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.status_code = status_code


class GovernedAIEndpointSafetyError(RuntimeError):
    def __init__(self, message: str, *, reason_code: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


def list_provider_connections(
    db: Session,
    *,
    organization_id: str,
) -> dict[str, object]:
    items = (
        db.query(GovernedAIProviderConnection)
        .filter(
            GovernedAIProviderConnection.organization_id == organization_id,
            GovernedAIProviderConnection.status != "disconnected",
        )
        .order_by(
            GovernedAIProviderConnection.created_at.asc(),
            GovernedAIProviderConnection.id.asc(),
        )
        .all()
    )
    return {
        "items": [_serialize(item) for item in items],
        "count": len(items),
        "truth": {
            "state": "candidate_only",
            "summary": (
                "Saved private AI providers are inactive until connection, safety, "
                "schema, quality, and latency checks pass in a later review."
            ),
        },
        "routing_enabled": False,
        "automatic_activation_allowed": False,
    }


def create_provider_connection(
    db: Session,
    *,
    organization_id: str,
    actor_user_id: str,
    name: str,
    endpoint_url: str,
    model_identifier: str,
    api_key: str | None,
) -> dict[str, object]:
    require_commercial_feature(
        db,
        organization_id=organization_id,
        feature_code=FEATURE_PRIVATE_AI_PROVIDER,
    )
    organization = db.get(Organization, organization_id)
    if organization is None:
        raise GovernedAIProviderConnectionError(
            "Organization not found.",
            reason_code="organization_not_found",
            status_code=404,
        )
    normalized_name = name.strip()
    if len(normalized_name) < 2 or len(normalized_name) > 120:
        raise GovernedAIProviderConnectionError(
            "The private AI provider name is invalid.",
            reason_code="ai_provider_identity_invalid",
            status_code=422,
        )
    normalized_model = model_identifier.strip()
    if not normalized_model or len(normalized_model) > 200:
        raise GovernedAIProviderConnectionError(
            "The AI model identifier is invalid.",
            reason_code="ai_provider_model_invalid",
            status_code=422,
        )
    try:
        normalized_endpoint = validate_openai_compatible_endpoint(endpoint_url)
    except GovernedAIProviderError as exc:
        raise GovernedAIProviderConnectionError(
            str(exc), reason_code=exc.code, status_code=422
        ) from exc
    endpoint_host = (urlsplit(normalized_endpoint).hostname or "").lower().rstrip(".")
    normalized_key = (api_key or "").strip()
    encrypted_blob, key_reference, key_version = encrypt_payload(
        {
            "schema_version": "governed-ai-provider-config-v1",
            "endpoint_url": normalized_endpoint,
            "api_key": normalized_key,
        }
    )
    now = datetime.now(UTC)
    row = GovernedAIProviderConnection(
        tenant_id=organization_id,
        organization_id=organization_id,
        name=normalized_name,
        adapter_type="openai_compatible",
        status="candidate",
        endpoint_host=endpoint_host,
        model_identifier=normalized_model,
        capabilities_json=json.dumps(_CAPABILITIES, separators=(",", ":")),
        encrypted_config_blob=encrypted_blob,
        key_reference=key_reference,
        key_version=key_version,
        credential_configured=bool(normalized_key),
        validation_status="not_tested",
        network_validation_status="not_tested",
        last_validation_reason=None,
        resolved_address_hash=None,
        activation_status="inactive",
        automatic_activation_allowed=False,
        created_by_user_id=actor_user_id,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise GovernedAIProviderConnectionError(
            "A private AI provider with this name already exists.",
            reason_code="ai_provider_name_conflict",
            status_code=409,
        ) from exc
    db.refresh(row)
    return {
        "created": True,
        "item": _serialize(row),
        "routing_enabled": False,
        "automatic_activation_allowed": False,
    }


def disconnect_provider_connection(
    db: Session,
    *,
    organization_id: str,
    connection_id: str,
    actor_user_id: str,
) -> dict[str, object]:
    row = (
        db.query(GovernedAIProviderConnection)
        .filter(
            GovernedAIProviderConnection.id == connection_id,
            GovernedAIProviderConnection.organization_id == organization_id,
        )
        .with_for_update()
        .one_or_none()
    )
    if row is None:
        raise GovernedAIProviderConnectionError(
            "Private AI provider not found.",
            reason_code="ai_provider_connection_not_found",
            status_code=404,
        )
    if row.status != "disconnected":
        now = datetime.now(UTC)
        row.status = "disconnected"
        row.encrypted_config_blob = None
        row.key_reference = None
        row.key_version = None
        row.credential_configured = False
        row.validation_status = "not_tested"
        row.network_validation_status = "not_tested"
        row.last_validation_reason = None
        row.resolved_address_hash = None
        row.activation_status = "inactive"
        row.automatic_activation_allowed = False
        row.disconnected_by_user_id = actor_user_id
        row.disconnected_at = now
        row.updated_at = now
        db.commit()
        db.refresh(row)
    return {
        "disconnected": True,
        "item": _serialize(row),
        "routing_enabled": False,
        "automatic_activation_allowed": False,
    }


def preflight_provider_connection(
    db: Session,
    *,
    organization_id: str,
    connection_id: str,
    resolver: Callable[..., list[tuple[object, ...]]] = socket.getaddrinfo,
) -> dict[str, object]:
    require_commercial_feature(
        db,
        organization_id=organization_id,
        feature_code=FEATURE_PRIVATE_AI_PROVIDER,
    )
    row = (
        db.query(GovernedAIProviderConnection)
        .filter(
            GovernedAIProviderConnection.id == connection_id,
            GovernedAIProviderConnection.organization_id == organization_id,
            GovernedAIProviderConnection.status == "candidate",
        )
        .with_for_update()
        .one_or_none()
    )
    if row is None or not row.encrypted_config_blob:
        raise GovernedAIProviderConnectionError(
            "Private AI provider not found.",
            reason_code="ai_provider_connection_not_found",
            status_code=404,
        )
    try:
        config = decrypt_payload(row.encrypted_config_blob)
    except CredentialCryptoError as exc:
        raise GovernedAIProviderConnectionError(
            "The private AI provider configuration is unavailable.",
            reason_code="ai_provider_configuration_unavailable",
            status_code=409,
        ) from exc
    endpoint_url = config.get("endpoint_url")
    if not isinstance(endpoint_url, str):
        raise GovernedAIProviderConnectionError(
            "The private AI provider configuration is unavailable.",
            reason_code="ai_provider_configuration_unavailable",
            status_code=409,
        )
    try:
        addresses = resolve_public_endpoint_addresses(endpoint_url, resolver=resolver)
    except GovernedAIEndpointSafetyError as exc:
        row.network_validation_status = "failed"
        row.last_validation_reason = exc.reason_code
        row.resolved_address_hash = None
        row.last_validated_at = datetime.now(UTC)
        row.updated_at = row.last_validated_at
        db.commit()
        db.refresh(row)
        return {
            "passed": False,
            "item": _serialize(row),
            "reason_code": exc.reason_code,
            "summary": "The endpoint hostname did not pass the public-network safety check.",
            "network_request_made": False,
            "routing_enabled": False,
            "automatic_activation_allowed": False,
        }
    now = datetime.now(UTC)
    row.network_validation_status = "passed"
    row.last_validation_reason = "ai_provider_public_dns_verified"
    row.resolved_address_hash = sha256(
        ",".join(addresses).encode("utf-8")
    ).hexdigest()
    row.last_validated_at = now
    row.updated_at = now
    db.commit()
    db.refresh(row)
    return {
        "passed": True,
        "item": _serialize(row),
        "reason_code": row.last_validation_reason,
        "summary": (
            "The hostname currently resolves only to public addresses. No model "
            "request was sent, and the provider remains inactive."
        ),
        "network_request_made": False,
        "routing_enabled": False,
        "automatic_activation_allowed": False,
    }


def resolve_public_endpoint_addresses(
    endpoint_url: str,
    *,
    resolver: Callable[..., list[tuple[object, ...]]] = socket.getaddrinfo,
) -> tuple[str, ...]:
    try:
        normalized_endpoint = validate_openai_compatible_endpoint(endpoint_url)
    except GovernedAIProviderError as exc:
        raise GovernedAIEndpointSafetyError(
            "The endpoint is not an approved HTTPS destination.",
            reason_code=exc.code,
        ) from exc
    hostname = (urlsplit(normalized_endpoint).hostname or "").lower().rstrip(".")
    try:
        records = resolver(hostname, 443, type=socket.SOCK_STREAM)
    except (OSError, socket.gaierror) as exc:
        raise GovernedAIEndpointSafetyError(
            "The endpoint hostname could not be resolved.",
            reason_code="ai_provider_dns_unavailable",
        ) from exc
    addresses: set[str] = set()
    for record in records:
        if len(record) < 5 or not isinstance(record[4], tuple) or not record[4]:
            continue
        candidate = str(record[4][0]).split("%", 1)[0]
        try:
            address = ipaddress.ip_address(candidate)
        except ValueError as exc:
            raise GovernedAIEndpointSafetyError(
                "The endpoint hostname returned an invalid address.",
                reason_code="ai_provider_dns_invalid",
            ) from exc
        if not address.is_global:
            raise GovernedAIEndpointSafetyError(
                "The endpoint hostname resolved to a blocked network.",
                reason_code="ai_provider_dns_private_or_reserved",
            )
        addresses.add(address.compressed)
    if not addresses:
        raise GovernedAIEndpointSafetyError(
            "The endpoint hostname returned no usable public address.",
            reason_code="ai_provider_dns_unavailable",
        )
    return tuple(sorted(addresses))


def _serialize(row: GovernedAIProviderConnection) -> dict[str, object]:
    try:
        capabilities = json.loads(row.capabilities_json)
    except (TypeError, ValueError):
        capabilities = []
    return {
        "id": row.id,
        "name": row.name,
        "adapter_type": row.adapter_type,
        "status": row.status,
        "endpoint_host": row.endpoint_host,
        "model_identifier": row.model_identifier,
        "capabilities": capabilities if isinstance(capabilities, list) else [],
        "credential_configured": row.credential_configured,
        "validation_status": row.validation_status,
        "network_validation_status": row.network_validation_status,
        "last_validation_reason": row.last_validation_reason,
        "activation_status": row.activation_status,
        "automatic_activation_allowed": False,
        "created_at": row.created_at.isoformat(),
        "last_validated_at": (
            row.last_validated_at.isoformat() if row.last_validated_at else None
        ),
        "candidate_only": True,
    }

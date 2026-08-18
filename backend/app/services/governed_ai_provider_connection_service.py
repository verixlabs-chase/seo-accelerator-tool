from __future__ import annotations

import ipaddress
import json
import socket
import ssl
from collections.abc import Callable, Iterable
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from time import perf_counter
from typing import Any, Iterator
from urllib.parse import urlsplit

import httpcore
import httpx
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.crypto import CredentialCryptoError, decrypt_payload, encrypt_payload
from app.models.governed_ai_provider_connection import GovernedAIProviderConnection
from app.models.organization import Organization
from app.services.audit_service import write_audit_log
from app.services.commercial_plan_service import (
    FEATURE_PRIVATE_AI_PROVIDER,
    require_commercial_feature,
)
from app.services.governed_ai_provider import (
    GovernedAIProviderError,
    OpenAICompatibleGovernedAIProvider,
    validate_openai_compatible_endpoint,
)


_CAPABILITIES = ("explain", "question_answer", "draft", "keyword_filter", "baseline")
_VALIDATION_SCHEMA_VERSION = "openai-compatible-connection-v1"
_VALIDATION_TIMEOUT_SECONDS = 10.0
_MAX_VALIDATION_RESPONSE_BYTES = 65_536
_VALIDATION_MARKER = "insightos_provider_validation_v1"


class GovernedAIProviderConnectionError(RuntimeError):
    def __init__(self, message: str, *, reason_code: str, status_code: int) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.status_code = status_code


class GovernedAIEndpointSafetyError(RuntimeError):
    def __init__(self, message: str, *, reason_code: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


class GovernedAIProviderTransportError(RuntimeError):
    def __init__(self, message: str, *, reason_code: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


@dataclass(frozen=True)
class ProviderValidationHTTPResult:
    status_code: int
    headers: dict[str, str]
    body: bytes
    elapsed_ms: int


class _PinnedNetworkBackend(httpcore.NetworkBackend):
    """Connect only to approved addresses while preserving hostname TLS/SNI."""

    def __init__(
        self,
        *,
        expected_hostname: str,
        approved_addresses: tuple[str, ...],
        backend: httpcore.NetworkBackend | None = None,
    ) -> None:
        self._expected_hostname = expected_hostname.lower().rstrip(".")
        self._approved_addresses = approved_addresses
        self._backend = backend or httpcore.SyncBackend()

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[tuple[Any, ...]] | None = None,
    ) -> httpcore.NetworkStream:
        normalized_host = host.lower().rstrip(".")
        if normalized_host != self._expected_hostname or port != 443:
            raise httpcore.ConnectError("The destination is outside the approved endpoint.")
        last_error: Exception | None = None
        for address in self._approved_addresses:
            try:
                return self._backend.connect_tcp(
                    address,
                    port,
                    timeout=timeout,
                    local_address=local_address,
                    socket_options=socket_options,
                )
            except httpcore.NetworkError as exc:
                last_error = exc
        if last_error is not None:
            raise last_error
        raise httpcore.ConnectError("The endpoint has no approved destination.")

    def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: Iterable[tuple[Any, ...]] | None = None,
    ) -> httpcore.NetworkStream:
        raise httpcore.ConnectError("Unix sockets are not approved destinations.")


class _PinnedHTTPTransport(httpx.BaseTransport):
    def __init__(
        self,
        *,
        hostname: str,
        approved_addresses: tuple[str, ...],
        max_response_bytes: int = _MAX_VALIDATION_RESPONSE_BYTES,
    ) -> None:
        self._max_response_bytes = max_response_bytes
        self._pool = httpcore.ConnectionPool(
            ssl_context=ssl.create_default_context(),
            max_connections=1,
            max_keepalive_connections=0,
            http1=True,
            http2=False,
            retries=0,
            network_backend=_PinnedNetworkBackend(
                expected_hostname=hostname,
                approved_addresses=approved_addresses,
            ),
        )

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        core_request = httpcore.Request(
            method=request.method,
            url=httpcore.URL(
                scheme=request.url.raw_scheme,
                host=request.url.raw_host,
                port=request.url.port,
                target=request.url.raw_path,
            ),
            headers=request.headers.raw,
            content=request.read(),
            extensions=request.extensions,
        )
        try:
            core_response = self._pool.handle_request(core_request)
        except httpcore.TimeoutException as exc:
            raise httpx.TimeoutException(str(exc), request=request) from exc
        except httpcore.NetworkError as exc:
            raise httpx.ConnectError(str(exc), request=request) from exc
        except httpcore.ProtocolError as exc:
            raise httpx.RemoteProtocolError(str(exc), request=request) from exc

        content = bytearray()
        try:
            for chunk in core_response.iter_stream():
                if len(content) + len(chunk) > self._max_response_bytes:
                    raise GovernedAIProviderTransportError(
                        "The provider validation response was too large.",
                        reason_code="ai_provider_response_too_large",
                    )
                content.extend(chunk)
        finally:
            core_response.close()
        return httpx.Response(
            status_code=core_response.status,
            headers=core_response.headers,
            content=bytes(content),
            extensions=core_response.extensions,
            request=request,
        )

    def close(self) -> None:
        self._pool.close()


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
                "A saved private AI provider is only a candidate identity. Its "
                "separately governed standby and limited-routing state determines "
                "whether it may receive a bounded prompt."
            ),
        },
        "routing_enabled": False,
        "routing_state_is_separate": True,
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
        last_validation_latency_ms=None,
        validation_schema_version=None,
        validation_evidence_hash=None,
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
        row.last_validation_latency_ms = None
        row.validation_schema_version = None
        row.validation_evidence_hash = None
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


def send_pinned_structured_request(
    *,
    endpoint_url: str,
    api_key: str,
    approved_addresses: tuple[str, ...],
    payload: dict[str, Any],
) -> ProviderValidationHTTPResult:
    hostname = (urlsplit(endpoint_url).hostname or "").lower().rstrip(".")
    transport = _PinnedHTTPTransport(
        hostname=hostname,
        approved_addresses=approved_addresses,
    )
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "user-agent": "InsightOS-Provider-Validation/1.0",
    }
    if api_key:
        headers["authorization"] = f"Bearer {api_key}"
    started = perf_counter()
    with httpx.Client(
        transport=transport,
        follow_redirects=False,
        trust_env=False,
        timeout=httpx.Timeout(_VALIDATION_TIMEOUT_SECONDS),
    ) as client:
        response = client.post(endpoint_url, headers=headers, json=payload)
    elapsed_ms = min(60_000, max(0, round((perf_counter() - started) * 1000)))
    return ProviderValidationHTTPResult(
        status_code=int(response.status_code),
        headers={key.lower(): value for key, value in response.headers.items()},
        body=response.content,
        elapsed_ms=elapsed_ms,
    )


@contextmanager
def open_pinned_runtime_provider(
    db: Session,
    *,
    organization_id: str,
    connection_id: str,
    timeout_seconds: float,
    max_output_tokens: int,
    resolver: Callable[..., list[tuple[object, ...]]] = socket.getaddrinfo,
) -> Iterator[OpenAICompatibleGovernedAIProvider]:
    """Build a one-attempt runtime adapter pinned to the current approved DNS set."""

    row = (
        db.query(GovernedAIProviderConnection)
        .filter(
            GovernedAIProviderConnection.id == connection_id,
            GovernedAIProviderConnection.organization_id == organization_id,
            GovernedAIProviderConnection.status == "candidate",
            GovernedAIProviderConnection.validation_status == "passed",
            GovernedAIProviderConnection.network_validation_status == "passed",
        )
        .one_or_none()
    )
    if row is None or not row.encrypted_config_blob or not row.resolved_address_hash:
        raise GovernedAIProviderConnectionError(
            "The private AI provider is no longer ready for a canary request.",
            reason_code="ai_provider_canary_connection_not_current",
            status_code=409,
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
    api_key = config.get("api_key")
    if not isinstance(endpoint_url, str) or not isinstance(api_key, str) or not api_key:
        raise GovernedAIProviderConnectionError(
            "The private AI provider credential is unavailable.",
            reason_code="ai_provider_configuration_unavailable",
            status_code=409,
        )
    try:
        addresses = resolve_public_endpoint_addresses(endpoint_url, resolver=resolver)
    except GovernedAIEndpointSafetyError as exc:
        raise GovernedAIProviderConnectionError(
            "The private AI endpoint no longer passes the public-network safety check.",
            reason_code=exc.reason_code,
            status_code=409,
        ) from exc
    current_hash = sha256(",".join(addresses).encode("utf-8")).hexdigest()
    if current_hash != row.resolved_address_hash:
        raise GovernedAIProviderConnectionError(
            "The private AI endpoint changed and must be validated again.",
            reason_code="ai_provider_canary_dns_changed",
            status_code=409,
        )
    hostname = (urlsplit(endpoint_url).hostname or "").lower().rstrip(".")
    transport = _PinnedHTTPTransport(
        hostname=hostname,
        approved_addresses=addresses,
    )
    client = httpx.Client(
        transport=transport,
        follow_redirects=False,
        trust_env=False,
        timeout=httpx.Timeout(min(10.0, max(1.0, timeout_seconds))),
    )
    try:
        yield OpenAICompatibleGovernedAIProvider(
            provider_name="private_ai",
            display_name="Private AI",
            api_key=api_key,
            endpoint=endpoint_url,
            model_name=row.model_identifier,
            timeout_seconds=min(10.0, max(1.0, timeout_seconds)),
            max_output_tokens=max_output_tokens,
            max_attempts=1,
            client=client,
        )
    finally:
        client.close()


def send_pinned_validation_request(
    *,
    endpoint_url: str,
    model_identifier: str,
    api_key: str,
    approved_addresses: tuple[str, ...],
) -> ProviderValidationHTTPResult:
    payload = {
        "model": model_identifier,
        "messages": [
            {
                "role": "system",
                "content": (
                    "This is a connection validation. Return only the requested "
                    "JSON object and do not perform any other task."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {"marker": _VALIDATION_MARKER},
                    separators=(",", ":"),
                    sort_keys=True,
                ),
            },
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "insightos_provider_validation",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "ok": {"const": True},
                        "marker": {"const": _VALIDATION_MARKER},
                    },
                    "required": ["ok", "marker"],
                    "additionalProperties": False,
                },
            },
        },
        "temperature": 0,
        "seed": 7,
        "max_tokens": 32,
    }
    return send_pinned_structured_request(
        endpoint_url=endpoint_url,
        api_key=api_key,
        approved_addresses=approved_addresses,
        payload=payload,
    )


def validate_provider_connection(
    db: Session,
    *,
    organization_id: str,
    connection_id: str,
    actor_user_id: str,
    resolver: Callable[..., list[tuple[object, ...]]] = socket.getaddrinfo,
    request_sender: Callable[..., ProviderValidationHTTPResult] = (
        send_pinned_validation_request
    ),
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
    api_key = config.get("api_key", "")
    if not isinstance(endpoint_url, str) or not isinstance(api_key, str):
        raise GovernedAIProviderConnectionError(
            "The private AI provider configuration is unavailable.",
            reason_code="ai_provider_configuration_unavailable",
            status_code=409,
        )

    try:
        addresses = resolve_public_endpoint_addresses(endpoint_url, resolver=resolver)
    except GovernedAIEndpointSafetyError as exc:
        row.network_validation_status = "failed"
        row.resolved_address_hash = None
        return _finish_provider_validation(
            db,
            row=row,
            actor_user_id=actor_user_id,
            passed=False,
            reason_code=exc.reason_code,
            summary="The endpoint did not pass the public-network safety check.",
            latency_ms=None,
            evidence_hash=None,
            network_request_made=False,
        )

    address_hash = sha256(",".join(addresses).encode("utf-8")).hexdigest()
    row.network_validation_status = "passed"
    row.resolved_address_hash = address_hash
    try:
        result = request_sender(
            endpoint_url=endpoint_url,
            model_identifier=row.model_identifier,
            api_key=api_key,
            approved_addresses=addresses,
        )
    except GovernedAIProviderTransportError as exc:
        return _finish_provider_validation(
            db,
            row=row,
            actor_user_id=actor_user_id,
            passed=False,
            reason_code=exc.reason_code,
            summary="The endpoint response did not pass the bounded safety check.",
            latency_ms=None,
            evidence_hash=None,
            network_request_made=True,
        )
    except httpx.TimeoutException:
        return _finish_provider_validation(
            db,
            row=row,
            actor_user_id=actor_user_id,
            passed=False,
            reason_code="ai_provider_connection_timeout",
            summary="The endpoint did not answer within the validation time limit.",
            latency_ms=None,
            evidence_hash=None,
            network_request_made=True,
        )
    except httpx.HTTPError:
        return _finish_provider_validation(
            db,
            row=row,
            actor_user_id=actor_user_id,
            passed=False,
            reason_code="ai_provider_connection_unavailable",
            summary="The endpoint could not complete the connection validation.",
            latency_ms=None,
            evidence_hash=None,
            network_request_made=True,
        )

    reason_code = _provider_response_failure_reason(result)
    if reason_code is not None:
        return _finish_provider_validation(
            db,
            row=row,
            actor_user_id=actor_user_id,
            passed=False,
            reason_code=reason_code,
            summary=_provider_validation_failure_summary(reason_code),
            latency_ms=result.elapsed_ms,
            evidence_hash=None,
            network_request_made=True,
        )

    evidence_hash = sha256(
        "|".join(
            (
                _VALIDATION_SCHEMA_VERSION,
                row.endpoint_host,
                row.model_identifier,
                address_hash,
                sha256(result.body).hexdigest(),
            )
        ).encode("utf-8")
    ).hexdigest()
    return _finish_provider_validation(
        db,
        row=row,
        actor_user_id=actor_user_id,
        passed=True,
        reason_code="ai_provider_connection_validated",
        summary=(
            "The endpoint passed the pinned connection and structured-response "
            "check. It remains inactive until a separate owner review."
        ),
        latency_ms=result.elapsed_ms,
        evidence_hash=evidence_hash,
        network_request_made=True,
    )


def _provider_response_failure_reason(
    result: ProviderValidationHTTPResult,
) -> str | None:
    if 300 <= result.status_code < 400:
        return "ai_provider_redirect_blocked"
    if result.status_code in {401, 403}:
        return "ai_provider_authentication_failed"
    if result.status_code < 200 or result.status_code >= 300:
        return "ai_provider_connection_rejected"
    content_type = result.headers.get("content-type", "").lower()
    if "application/json" not in content_type:
        return "ai_provider_schema_incompatible"
    try:
        payload = json.loads(result.body)
        choices = payload["choices"]
        content = choices[0]["message"]["content"]
        validated = json.loads(content)
    except (IndexError, KeyError, TypeError, ValueError):
        return "ai_provider_schema_incompatible"
    if validated != {"ok": True, "marker": _VALIDATION_MARKER}:
        return "ai_provider_schema_incompatible"
    return None


def _provider_validation_failure_summary(reason_code: str) -> str:
    summaries = {
        "ai_provider_redirect_blocked": (
            "The endpoint attempted to redirect the validation request. Redirects are blocked."
        ),
        "ai_provider_authentication_failed": (
            "The endpoint rejected the saved connection credential."
        ),
        "ai_provider_schema_incompatible": (
            "The endpoint did not return the required structured response."
        ),
    }
    return summaries.get(
        reason_code,
        "The endpoint rejected the bounded connection validation.",
    )


def _finish_provider_validation(
    db: Session,
    *,
    row: GovernedAIProviderConnection,
    actor_user_id: str,
    passed: bool,
    reason_code: str,
    summary: str,
    latency_ms: int | None,
    evidence_hash: str | None,
    network_request_made: bool,
) -> dict[str, object]:
    now = datetime.now(UTC)
    normalized_latency = (
        min(60_000, max(0, int(latency_ms))) if latency_ms is not None else None
    )
    row.validation_status = "passed" if passed else "failed"
    row.last_validation_reason = reason_code
    row.last_validation_latency_ms = normalized_latency
    row.validation_schema_version = _VALIDATION_SCHEMA_VERSION
    row.validation_evidence_hash = evidence_hash if passed else None
    row.last_validated_at = now
    row.updated_at = now
    row.activation_status = "inactive"
    row.automatic_activation_allowed = False
    write_audit_log(
        db,
        tenant_id=row.organization_id,
        actor_user_id=actor_user_id,
        event_type=(
            "ai.provider_connection.validation_passed"
            if passed
            else "ai.provider_connection.validation_failed"
        ),
        payload={
            "connection_id": row.id,
            "reason_code": reason_code,
            "latency_ms": normalized_latency,
            "network_request_made": network_request_made,
            "schema_version": _VALIDATION_SCHEMA_VERSION,
            "routing_enabled": False,
        },
    )
    db.commit()
    db.refresh(row)
    return {
        "passed": passed,
        "item": _serialize(row),
        "reason_code": reason_code,
        "summary": summary,
        "network_request_made": network_request_made,
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
        "last_validation_latency_ms": row.last_validation_latency_ms,
        "validation_schema_version": row.validation_schema_version,
        "activation_status": row.activation_status,
        "automatic_activation_allowed": False,
        "created_at": row.created_at.isoformat(),
        "last_validated_at": (
            row.last_validated_at.isoformat() if row.last_validated_at else None
        ),
        "candidate_only": True,
    }

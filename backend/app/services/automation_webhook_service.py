from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
import re
import time
from typing import Any
from urllib.parse import urlsplit, urlunsplit
import uuid

import httpx
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.automation import (
    AUTOMATION_EVENT_SCHEMA_VERSION,
    AutomationEventEnvelope,
    automation_event_catalog,
    build_automation_event,
    generate_signing_secret,
    sign_automation_event,
)
from app.core.crypto import CredentialCryptoError, decrypt_payload, encrypt_payload
from app.models.automation_webhook import (
    AutomationWebhookConnection,
    AutomationWebhookDelivery,
    AutomationWebhookDeliveryAttempt,
)
from app.models.organization import Organization
from app.services.audit_service import write_audit_log
from app.services.commercial_plan_service import (
    FEATURE_EXTERNAL_AUTOMATION,
    CostEconomicsError,
    require_commercial_feature,
)


AUTOMATION_DELIVERY_TIMEOUT_SECONDS = 10.0
AUTOMATION_DELIVERY_MAX_ATTEMPTS = 3
_PROVIDERS = {"zapier": "Zapier", "make": "Make", "pipedream": "Pipedream"}
_PIPEDREAM_HOST = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}\.m\.pipedream\.net$")
_MAKE_HOST = re.compile(r"^hook(?:\.[a-z0-9-]+)?\.make\.com$")


class AutomationWebhookError(RuntimeError):
    def __init__(self, message: str, *, reason_code: str, status_code: int = 409) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.status_code = status_code


def list_connections(db: Session, *, organization_id: str) -> dict[str, Any]:
    rows = (
        db.query(AutomationWebhookConnection)
        .filter(AutomationWebhookConnection.organization_id == organization_id)
        .order_by(AutomationWebhookConnection.created_at.asc())
        .all()
    )
    return {
        "items": [_serialize_connection(db, row) for row in rows],
        "supported_providers": [
            {"code": code, "label": label} for code, label in _PROVIDERS.items()
        ],
        "supported_events": automation_event_catalog(),
        "automatic_actions_enabled": False,
        "truth": (
            "Only signed outbound events are available. Connected tools cannot approve, "
            "publish, change a website, or change a business profile."
        ),
    }


def create_connection(
    db: Session,
    *,
    organization_id: str,
    actor_user_id: str,
    name: str,
    provider: str,
    destination_url: str,
    event_types: list[str],
) -> dict[str, Any]:
    organization = _locked_organization(db, organization_id)
    _require_feature(db, organization_id)
    normalized_name = " ".join(str(name or "").split())
    if not 2 <= len(normalized_name) <= 120:
        raise AutomationWebhookError(
            "Give this connection a name between 2 and 120 characters.",
            reason_code="automation_connection_name_invalid",
            status_code=422,
        )
    normalized_provider = str(provider or "").strip().lower()
    destination, endpoint_host = validate_automation_destination(
        provider=normalized_provider,
        destination_url=destination_url,
    )
    approved_events = _validate_event_types(event_types)
    existing = (
        db.query(AutomationWebhookConnection.id)
        .filter(
            AutomationWebhookConnection.organization_id == organization_id,
            AutomationWebhookConnection.name == normalized_name,
        )
        .first()
    )
    if existing is not None:
        raise AutomationWebhookError(
            "A connection with this name already exists.",
            reason_code="automation_connection_name_exists",
        )

    signing_secret = generate_signing_secret()
    encrypted_blob, key_reference, key_version = _encrypt_config(
        {"destination_url": destination, "signing_secret": signing_secret}
    )
    now = datetime.now(UTC)
    row = AutomationWebhookConnection(
        id=str(uuid.uuid4()),
        tenant_id=organization.id,
        organization_id=organization.id,
        name=normalized_name,
        provider=normalized_provider,
        status="pending",
        endpoint_host=endpoint_host,
        event_types_json=json.dumps(approved_events, separators=(",", ":")),
        encrypted_config_blob=encrypted_blob,
        key_reference=key_reference,
        key_version=key_version,
        signing_secret_version=1,
        verification_status="not_tested",
        consecutive_failures=0,
        created_by_user_id=actor_user_id,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    write_audit_log(
        db,
        tenant_id=organization.id,
        actor_user_id=actor_user_id,
        event_type="automation.webhook_connection.created",
        payload={
            "connection_id": row.id,
            "provider": row.provider,
            "endpoint_host": row.endpoint_host,
            "event_types": approved_events,
        },
    )
    db.commit()
    db.refresh(row)
    return {
        "connection": _serialize_connection(db, row),
        "signing_secret": signing_secret,
        "secret_shown_once": True,
        "next_step": "Save the signing secret, then send a test event.",
    }


def rotate_signing_secret(
    db: Session,
    *,
    organization_id: str,
    connection_id: str,
    actor_user_id: str,
) -> dict[str, Any]:
    row = _locked_connection(db, organization_id=organization_id, connection_id=connection_id)
    _require_connected_config(row)
    config = _decrypt_config(row.encrypted_config_blob)
    signing_secret = generate_signing_secret()
    encrypted_blob, key_reference, key_version = _encrypt_config(
        {
            "destination_url": str(config["destination_url"]),
            "signing_secret": signing_secret,
        }
    )
    now = datetime.now(UTC)
    row.encrypted_config_blob = encrypted_blob
    row.key_reference = key_reference
    row.key_version = key_version
    row.signing_secret_version += 1
    row.status = "pending"
    row.verification_status = "not_tested"
    row.updated_at = now
    write_audit_log(
        db,
        tenant_id=organization_id,
        actor_user_id=actor_user_id,
        event_type="automation.webhook_connection.secret_rotated",
        payload={
            "connection_id": row.id,
            "provider": row.provider,
            "signing_secret_version": row.signing_secret_version,
        },
    )
    db.commit()
    db.refresh(row)
    return {
        "connection": _serialize_connection(db, row),
        "signing_secret": signing_secret,
        "secret_shown_once": True,
        "next_step": "Replace the old secret in your workflow, then send a new test event.",
    }


def disconnect_connection(
    db: Session,
    *,
    organization_id: str,
    connection_id: str,
    actor_user_id: str,
) -> dict[str, Any]:
    row = _locked_connection(db, organization_id=organization_id, connection_id=connection_id)
    now = datetime.now(UTC)
    if row.status != "disconnected":
        row.status = "disconnected"
        row.verification_status = "not_tested"
        row.encrypted_config_blob = None
        row.key_reference = None
        row.key_version = None
        row.disconnected_by_user_id = actor_user_id
        row.disconnected_at = now
        row.updated_at = now
        write_audit_log(
            db,
            tenant_id=organization_id,
            actor_user_id=actor_user_id,
            event_type="automation.webhook_connection.disconnected",
            payload={"connection_id": row.id, "provider": row.provider},
        )
        db.commit()
        db.refresh(row)
    return {"connection": _serialize_connection(db, row), "secrets_removed": True}


def send_test_delivery(
    db: Session,
    *,
    organization_id: str,
    connection_id: str,
    actor_user_id: str,
) -> dict[str, Any]:
    row = _locked_connection(db, organization_id=organization_id, connection_id=connection_id)
    _require_feature(db, organization_id)
    _require_connected_config(row)
    now = datetime.now(UTC)
    event = build_automation_event(
        event_id=f"evt_automation_test_{uuid.uuid4().hex}",
        event_type="connection.health_changed",
        occurred_at=now,
        organization_id=organization_id,
        location_id=None,
        truth_state="in_progress",
        resource_type="connection",
        resource_id=row.id,
        resource_href="/settings#external-automation",
        data={
            "connection_name": row.name,
            "state": "test",
            "summary": "InsightOS sent this signed test event to verify the connection.",
            "recovery_href": "/settings#external-automation",
        },
    )
    event_json = event.model_dump(mode="json")
    encrypted_event_blob, _, _ = _encrypt_config({"event": event_json})
    event_bytes = json.dumps(
        event_json, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    delivery = AutomationWebhookDelivery(
        id=str(uuid.uuid4()),
        tenant_id=row.tenant_id,
        organization_id=row.organization_id,
        connection_id=row.id,
        event_id=event.event_id,
        event_type=event.event_type,
        schema_version=AUTOMATION_EVENT_SCHEMA_VERSION,
        status="pending",
        encrypted_event_blob=encrypted_event_blob,
        event_hash=hashlib.sha256(event_bytes).hexdigest(),
        attempt_count=0,
        max_attempts=AUTOMATION_DELIVERY_MAX_ATTEMPTS,
        created_by_user_id=actor_user_id,
        created_at=now,
        updated_at=now,
    )
    db.add(delivery)
    write_audit_log(
        db,
        tenant_id=organization_id,
        actor_user_id=actor_user_id,
        event_type="automation.webhook_delivery.created",
        payload={
            "connection_id": row.id,
            "delivery_id": delivery.id,
            "event_id": delivery.event_id,
            "event_type": delivery.event_type,
        },
    )
    db.commit()
    return _attempt_delivery(
        db,
        organization_id=organization_id,
        delivery_id=delivery.id,
        actor_user_id=actor_user_id,
    )


def retry_delivery(
    db: Session,
    *,
    organization_id: str,
    delivery_id: str,
    actor_user_id: str,
) -> dict[str, Any]:
    return _attempt_delivery(
        db,
        organization_id=organization_id,
        delivery_id=delivery_id,
        actor_user_id=actor_user_id,
        retry=True,
    )


def list_deliveries(
    db: Session,
    *,
    organization_id: str,
    connection_id: str | None = None,
) -> dict[str, Any]:
    query = db.query(AutomationWebhookDelivery).filter(
        AutomationWebhookDelivery.organization_id == organization_id
    )
    if connection_id:
        query = query.filter(AutomationWebhookDelivery.connection_id == connection_id)
    rows = query.order_by(AutomationWebhookDelivery.created_at.desc()).limit(50).all()
    return {"items": [_serialize_delivery(db, row) for row in rows]}


def validate_automation_destination(*, provider: str, destination_url: str) -> tuple[str, str]:
    if provider not in _PROVIDERS:
        raise AutomationWebhookError(
            "Choose Zapier, Make, or Pipedream.",
            reason_code="automation_provider_not_supported",
            status_code=422,
        )
    raw = str(destination_url or "").strip()
    if not raw or len(raw) > 2_000 or any(character.isspace() for character in raw):
        raise _destination_error()
    try:
        parsed = urlsplit(raw)
        port = parsed.port
    except ValueError as exc:
        raise _destination_error() from exc
    host = str(parsed.hostname or "").lower().rstrip(".")
    if (
        parsed.scheme.lower() != "https"
        or not host
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or port not in {None, 443}
    ):
        raise _destination_error()
    if provider in {"zapier", "make"} and parsed.path in {"", "/"}:
        raise _destination_error()
    valid = False
    if provider == "zapier":
        valid = host == "hooks.zapier.com" and parsed.path.startswith("/hooks/catch/")
    elif provider == "make":
        valid = _MAKE_HOST.fullmatch(host) is not None and parsed.path not in {"", "/"}
    elif provider == "pipedream":
        valid = _PIPEDREAM_HOST.fullmatch(host) is not None
    if not valid:
        raise AutomationWebhookError(
            f"This is not a supported {_PROVIDERS[provider]} webhook URL.",
            reason_code="automation_destination_provider_mismatch",
            status_code=422,
        )
    canonical = urlunsplit(("https", host, parsed.path, parsed.query, ""))
    return canonical, host


def _attempt_delivery(
    db: Session,
    *,
    organization_id: str,
    delivery_id: str,
    actor_user_id: str,
    retry: bool = False,
) -> dict[str, Any]:
    delivery = (
        db.query(AutomationWebhookDelivery)
        .filter(
            AutomationWebhookDelivery.id == delivery_id,
            AutomationWebhookDelivery.organization_id == organization_id,
        )
        .populate_existing()
        .with_for_update()
        .first()
    )
    if delivery is None:
        raise AutomationWebhookError(
            "Automation delivery not found.",
            reason_code="automation_delivery_not_found",
            status_code=404,
        )
    if delivery.status == "delivered":
        if retry:
            raise AutomationWebhookError(
                "This event was already delivered and will not be sent twice.",
                reason_code="automation_delivery_already_delivered",
            )
        return {"delivery": _serialize_delivery(db, delivery)}
    recoverable_pending = delivery.status == "pending" and delivery.attempt_count == 0
    if retry and delivery.status != "failed" and not recoverable_pending:
        raise AutomationWebhookError(
            "Only a failed or interrupted delivery can be retried.",
            reason_code="automation_delivery_not_retryable",
        )
    if delivery.attempt_count >= delivery.max_attempts:
        raise AutomationWebhookError(
            "This delivery reached its retry limit. Create a new test after checking the workflow.",
            reason_code="automation_delivery_retry_limit",
        )
    connection = _locked_connection(
        db,
        organization_id=organization_id,
        connection_id=delivery.connection_id,
    )
    _require_feature(db, organization_id)
    _require_connected_config(connection)
    config = _decrypt_config(connection.encrypted_config_blob)
    destination, host = validate_automation_destination(
        provider=connection.provider,
        destination_url=str(config.get("destination_url") or ""),
    )
    if host != connection.endpoint_host:
        raise AutomationWebhookError(
            "The saved destination no longer matches this connection.",
            reason_code="automation_destination_identity_mismatch",
        )
    try:
        event_payload = _decrypt_config(delivery.encrypted_event_blob).get("event")
        event = AutomationEventEnvelope.model_validate(event_payload)
    except (CredentialCryptoError, ValidationError, TypeError, ValueError) as exc:
        raise AutomationWebhookError(
            "The saved event cannot be delivered safely.",
            reason_code="automation_delivery_event_invalid",
        ) from exc
    signed = sign_automation_event(
        event,
        signing_secret=str(config.get("signing_secret") or ""),
    )
    attempt_number = delivery.attempt_count + 1
    attempted_at = datetime.now(UTC)
    delivery.attempt_count = attempt_number
    delivery.status = "pending"
    delivery.last_attempt_at = attempted_at
    delivery.updated_at = attempted_at
    db.flush()

    started = time.monotonic()
    response_status: int | None = None
    reason_code: str | None = None
    delivered = False
    try:
        response_status = _post_signed_event(
            destination_url=destination,
            body=signed.body,
            headers=signed.headers,
        )
        delivered = 200 <= response_status < 300
        if not delivered:
            reason_code = "automation_destination_rejected"
    except (httpx.TimeoutException, httpx.NetworkError):
        reason_code = "automation_destination_unreachable"
    except httpx.HTTPError:
        reason_code = "automation_delivery_failed"
    duration_ms = max(0, int((time.monotonic() - started) * 1_000))
    now = datetime.now(UTC)
    attempt = AutomationWebhookDeliveryAttempt(
        id=str(uuid.uuid4()),
        tenant_id=delivery.tenant_id,
        organization_id=delivery.organization_id,
        delivery_id=delivery.id,
        attempt_number=attempt_number,
        status="delivered" if delivered else "failed",
        response_status=response_status,
        reason_code=reason_code,
        duration_ms=duration_ms,
        attempted_at=now,
    )
    db.add(attempt)
    delivery.status = "delivered" if delivered else "failed"
    delivery.last_reason_code = reason_code
    delivery.last_response_status = response_status
    delivery.delivered_at = now if delivered else None
    delivery.updated_at = now
    connection.last_tested_at = now
    connection.updated_at = now
    if delivered:
        connection.status = "active"
        connection.verification_status = "verified"
        connection.consecutive_failures = 0
        connection.last_success_at = now
    else:
        connection.status = "unhealthy"
        connection.verification_status = "failed"
        connection.consecutive_failures += 1
        connection.last_failure_at = now
    write_audit_log(
        db,
        tenant_id=organization_id,
        actor_user_id=actor_user_id,
        event_type=(
            "automation.webhook_delivery.delivered"
            if delivered
            else "automation.webhook_delivery.failed"
        ),
        payload={
            "connection_id": connection.id,
            "delivery_id": delivery.id,
            "event_id": delivery.event_id,
            "attempt_number": attempt_number,
            "response_status": response_status,
            "reason_code": reason_code,
        },
    )
    db.commit()
    db.refresh(delivery)
    return {
        "delivery": _serialize_delivery(db, delivery),
        "connection": _serialize_connection(db, connection),
        "received_by_destination": delivered,
    }


def _post_signed_event(
    *,
    destination_url: str,
    body: bytes,
    headers: dict[str, str],
) -> int:
    with httpx.Client(
        timeout=AUTOMATION_DELIVERY_TIMEOUT_SECONDS,
        follow_redirects=False,
    ) as client:
        response = client.post(destination_url, content=body, headers=headers)
    return int(response.status_code)


def _serialize_connection(
    db: Session, row: AutomationWebhookConnection
) -> dict[str, Any]:
    last_delivery = (
        db.query(AutomationWebhookDelivery)
        .filter(AutomationWebhookDelivery.connection_id == row.id)
        .order_by(AutomationWebhookDelivery.created_at.desc())
        .first()
    )
    return {
        "id": row.id,
        "name": row.name,
        "provider": row.provider,
        "provider_label": _PROVIDERS.get(row.provider, "Automation tool"),
        "status": row.status,
        "endpoint_host": row.endpoint_host,
        "event_types": _event_types(row.event_types_json),
        "verification_status": row.verification_status,
        "signing_secret_version": row.signing_secret_version,
        "last_tested_at": _iso(row.last_tested_at),
        "last_success_at": _iso(row.last_success_at),
        "last_failure_at": _iso(row.last_failure_at),
        "created_at": _iso(row.created_at),
        "disconnected_at": _iso(row.disconnected_at),
        "destination_url_saved": bool(row.encrypted_config_blob),
        "destination_url_revealed": False,
        "last_delivery": _serialize_delivery(db, last_delivery) if last_delivery else None,
        "automatic_actions_enabled": False,
    }


def _serialize_delivery(
    db: Session, row: AutomationWebhookDelivery
) -> dict[str, Any]:
    attempts = (
        db.query(AutomationWebhookDeliveryAttempt)
        .filter(AutomationWebhookDeliveryAttempt.delivery_id == row.id)
        .order_by(AutomationWebhookDeliveryAttempt.attempt_number.asc())
        .all()
    )
    return {
        "id": row.id,
        "connection_id": row.connection_id,
        "event_id": row.event_id,
        "event_type": row.event_type,
        "schema_version": row.schema_version,
        "status": row.status,
        "attempt_count": row.attempt_count,
        "max_attempts": row.max_attempts,
        "last_reason_code": row.last_reason_code,
        "last_response_status": row.last_response_status,
        "last_attempt_at": _iso(row.last_attempt_at),
        "delivered_at": _iso(row.delivered_at),
        "created_at": _iso(row.created_at),
        "can_retry": (
            row.status == "failed"
            or (row.status == "pending" and row.attempt_count == 0)
        )
        and row.attempt_count < row.max_attempts,
        "attempts": [
            {
                "attempt_number": item.attempt_number,
                "status": item.status,
                "response_status": item.response_status,
                "reason_code": item.reason_code,
                "duration_ms": item.duration_ms,
                "attempted_at": _iso(item.attempted_at),
            }
            for item in attempts
        ],
    }


def _locked_organization(db: Session, organization_id: str) -> Organization:
    row = (
        db.query(Organization)
        .filter(Organization.id == organization_id)
        .with_for_update()
        .first()
    )
    if row is None:
        raise AutomationWebhookError(
            "Organization not found.",
            reason_code="organization_not_found",
            status_code=404,
        )
    return row


def _locked_connection(
    db: Session, *, organization_id: str, connection_id: str
) -> AutomationWebhookConnection:
    row = (
        db.query(AutomationWebhookConnection)
        .filter(
            AutomationWebhookConnection.id == connection_id,
            AutomationWebhookConnection.organization_id == organization_id,
        )
        .with_for_update()
        .first()
    )
    if row is None:
        raise AutomationWebhookError(
            "Automation connection not found.",
            reason_code="automation_connection_not_found",
            status_code=404,
        )
    return row


def _require_feature(db: Session, organization_id: str) -> None:
    try:
        require_commercial_feature(
            db,
            organization_id=organization_id,
            feature_code=FEATURE_EXTERNAL_AUTOMATION,
        )
    except CostEconomicsError as exc:
        raise AutomationWebhookError(
            str(exc), reason_code=exc.reason_code, status_code=exc.status_code
        ) from exc


def _require_connected_config(row: AutomationWebhookConnection) -> None:
    if row.status == "disconnected" or not row.encrypted_config_blob:
        raise AutomationWebhookError(
            "This automation connection is disconnected.",
            reason_code="automation_connection_disconnected",
        )


def _validate_event_types(values: list[str]) -> list[str]:
    approved = {item["code"] for item in automation_event_catalog()}
    normalized = sorted({str(value or "").strip() for value in values if str(value or "").strip()})
    if not normalized or any(value not in approved for value in normalized):
        raise AutomationWebhookError(
            "Choose at least one approved automation event.",
            reason_code="automation_event_subscription_invalid",
            status_code=422,
        )
    return normalized


def _event_types(raw: str) -> list[str]:
    try:
        values = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return [str(value) for value in values] if isinstance(values, list) else []


def _encrypt_config(data: dict[str, Any]) -> tuple[str, str, str]:
    try:
        return encrypt_payload(data)
    except CredentialCryptoError as exc:
        raise AutomationWebhookError(
            "Secure connection storage is not configured.",
            reason_code=exc.reason_code,
        ) from exc


def _decrypt_config(blob: str | None) -> dict[str, Any]:
    if not blob:
        raise AutomationWebhookError(
            "This automation connection has no saved destination.",
            reason_code="automation_connection_disconnected",
        )
    try:
        return decrypt_payload(blob)
    except CredentialCryptoError as exc:
        raise AutomationWebhookError(
            "This automation connection cannot be opened safely.",
            reason_code="automation_connection_secret_unavailable",
        ) from exc


def _destination_error() -> AutomationWebhookError:
    return AutomationWebhookError(
        "Use the complete HTTPS webhook URL supplied by Zapier, Make, or Pipedream.",
        reason_code="automation_destination_invalid",
        status_code=422,
    )


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return aware.isoformat()

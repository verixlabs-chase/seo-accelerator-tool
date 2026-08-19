from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import hmac
import json
import math
import re
import secrets
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


AUTOMATION_EVENT_SCHEMA_VERSION = "insightos.automation.event.v1"
AUTOMATION_SIGNATURE_VERSION = "v1"
AUTOMATION_SIGNATURE_TOLERANCE_SECONDS = 300
MAX_EVENT_BODY_BYTES = 32_768
MAX_DATA_DEPTH = 4
MAX_COLLECTION_ITEMS = 50
MAX_TEXT_LENGTH = 2_000

_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_SIGNATURE_PATTERN = re.compile(r"^v1=([0-9a-f]{64})$")
_FORBIDDEN_DATA_KEYS = {
    "access_token",
    "api_key",
    "authorization",
    "cookie",
    "credential",
    "email",
    "form_data",
    "internal_cost",
    "oauth_token",
    "password",
    "phone",
    "prompt",
    "provider_payload",
    "raw_content",
    "raw_html",
    "refresh_token",
    "secret",
    "session",
    "supplier",
}
_FORBIDDEN_KEY_SUFFIXES = (
    "_api_key",
    "_credential",
    "_email",
    "_password",
    "_phone",
    "_secret",
    "_token",
)


@dataclass(frozen=True)
class AutomationEventDefinition:
    code: str
    label: str
    summary: str
    resource_type: str
    allowed_data_fields: frozenset[str]


_EVENT_DEFINITIONS: tuple[AutomationEventDefinition, ...] = (
    AutomationEventDefinition(
        code="report.ready",
        label="Report ready",
        summary="A saved report is ready for the owner to review or share.",
        resource_type="report",
        allowed_data_fields=frozenset(
            {"report_id", "report_label", "observed_through", "summary", "report_href"}
        ),
    ),
    AutomationEventDefinition(
        code="recommendation.ready",
        label="Recommendation ready",
        summary="A saved, evidence-backed recommendation is ready for review.",
        resource_type="recommendation",
        allowed_data_fields=frozenset(
            {"recommendation_id", "title", "priority", "summary", "recommendation_href"}
        ),
    ),
    AutomationEventDefinition(
        code="review.saved",
        label="Review saved",
        summary="A saved customer rating is ready for private workflow routing.",
        resource_type="review",
        allowed_data_fields=frozenset(
            {"review_id", "rating", "response_status", "reviewed_at", "review_href"}
        ),
    ),
    AutomationEventDefinition(
        code="approval.requested",
        label="Approval requested",
        summary="A governed action is waiting for an authorized person.",
        resource_type="approval",
        allowed_data_fields=frozenset(
            {"approval_id", "title", "summary", "approval_href"}
        ),
    ),
    AutomationEventDefinition(
        code="action.completed",
        label="Action completed",
        summary="An approved action finished and saved its result.",
        resource_type="action",
        allowed_data_fields=frozenset(
            {"action_id", "title", "completed_at", "result_summary", "action_href"}
        ),
    ),
    AutomationEventDefinition(
        code="action.failed",
        label="Action needs attention",
        summary="An approved action stopped and has a saved recovery step.",
        resource_type="action",
        allowed_data_fields=frozenset(
            {"action_id", "title", "failed_at", "summary", "recovery", "action_href"}
        ),
    ),
    AutomationEventDefinition(
        code="connection.health_changed",
        label="Connection status changed",
        summary="A connected data source needs attention or has recovered.",
        resource_type="connection",
        allowed_data_fields=frozenset(
            {"connection_name", "state", "summary", "recovery_href"}
        ),
    ),
)
_EVENT_BY_CODE = {item.code: item for item in _EVENT_DEFINITIONS}


class AutomationContractError(RuntimeError):
    def __init__(self, message: str, *, reason_code: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


class AutomationResourceReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["report", "recommendation", "review", "approval", "action", "connection"]
    id: str = Field(min_length=1, max_length=80)
    href: str = Field(min_length=1, max_length=500)

    @field_validator("href")
    @classmethod
    def _same_product_path(cls, value: str) -> str:
        if not value.startswith("/") or value.startswith("//") or "://" in value:
            raise ValueError("Resource links must be relative InsightOS paths.")
        return value


class AutomationEventEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["insightos.automation.event.v1"]
    event_id: str = Field(min_length=1, max_length=80)
    event_type: str = Field(min_length=1, max_length=80)
    occurred_at: datetime
    organization_id: str = Field(min_length=1, max_length=80)
    location_id: str | None = Field(default=None, max_length=80)
    truth_state: Literal[
        "ready",
        "needs_attention",
        "in_progress",
        "completed",
        "failed",
        "blocked",
        "unavailable",
    ]
    resource: AutomationResourceReference
    data: dict[str, Any]

    @field_validator("occurred_at")
    @classmethod
    def _timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurred_at must include a timezone.")
        return value.astimezone(UTC)


@dataclass(frozen=True)
class SignedAutomationEvent:
    body: bytes
    headers: dict[str, str]


def automation_event_catalog() -> list[dict[str, str]]:
    return [
        {"code": item.code, "label": item.label, "summary": item.summary}
        for item in _EVENT_DEFINITIONS
    ]


def build_automation_event(
    *,
    event_id: str,
    event_type: str,
    occurred_at: datetime,
    organization_id: str,
    location_id: str | None,
    truth_state: str,
    resource_type: str,
    resource_id: str,
    resource_href: str,
    data: dict[str, Any],
) -> AutomationEventEnvelope:
    definition = _EVENT_BY_CODE.get(event_type)
    if definition is None:
        raise AutomationContractError(
            "This event type is not approved for external automation.",
            reason_code="automation_event_type_not_approved",
        )
    if resource_type != definition.resource_type:
        raise AutomationContractError(
            "The event resource type does not match the approved contract.",
            reason_code="automation_event_resource_mismatch",
        )
    unexpected = sorted(set(data) - definition.allowed_data_fields)
    if unexpected:
        raise AutomationContractError(
            "The event contains fields that are not approved for external automation.",
            reason_code="automation_event_fields_not_approved",
        )
    _validate_minimized_value(data, path="data", depth=0)
    try:
        return AutomationEventEnvelope(
            schema_version=AUTOMATION_EVENT_SCHEMA_VERSION,
            event_id=event_id,
            event_type=event_type,
            occurred_at=occurred_at,
            organization_id=organization_id,
            location_id=location_id,
            truth_state=truth_state,
            resource={"type": resource_type, "id": resource_id, "href": resource_href},
            data=data,
        )
    except ValidationError as exc:
        raise AutomationContractError(
            "The event does not match the approved external automation contract.",
            reason_code="automation_event_contract_invalid",
        ) from exc


def generate_signing_secret() -> str:
    return secrets.token_urlsafe(32)


def sign_automation_event(
    event: AutomationEventEnvelope,
    *,
    signing_secret: str,
    timestamp: int | None = None,
) -> SignedAutomationEvent:
    secret = _signing_secret_bytes(signing_secret)
    request_timestamp = timestamp if timestamp is not None else int(datetime.now(UTC).timestamp())
    body = _canonical_event_body(event)
    signature = hmac.new(
        secret,
        msg=str(request_timestamp).encode("ascii") + b"." + body,
        digestmod=hashlib.sha256,
    ).hexdigest()
    return SignedAutomationEvent(
        body=body,
        headers={
            "Content-Type": "application/json",
            "X-InsightOS-Event-ID": event.event_id,
            "X-InsightOS-Schema": event.schema_version,
            "X-InsightOS-Timestamp": str(request_timestamp),
            "X-InsightOS-Signature": f"{AUTOMATION_SIGNATURE_VERSION}={signature}",
        },
    )


def verify_signed_automation_event(
    *,
    body: bytes,
    headers: dict[str, str],
    signing_secret: str,
    now: datetime | None = None,
) -> AutomationEventEnvelope:
    if len(body) > MAX_EVENT_BODY_BYTES:
        raise AutomationContractError(
            "The automation event is larger than the supported contract.",
            reason_code="automation_event_too_large",
        )
    normalized_headers = {key.lower(): value.strip() for key, value in headers.items()}
    timestamp_value = normalized_headers.get("x-insightos-timestamp", "")
    signature_value = normalized_headers.get("x-insightos-signature", "")
    match = _SIGNATURE_PATTERN.fullmatch(signature_value)
    try:
        request_timestamp = int(timestamp_value)
    except (TypeError, ValueError) as exc:
        raise AutomationContractError(
            "The automation event timestamp is invalid.",
            reason_code="automation_event_timestamp_invalid",
        ) from exc
    if match is None:
        raise AutomationContractError(
            "The automation event signature is invalid.",
            reason_code="automation_event_signature_invalid",
        )
    current = int((now or datetime.now(UTC)).timestamp())
    if abs(current - request_timestamp) > AUTOMATION_SIGNATURE_TOLERANCE_SECONDS:
        raise AutomationContractError(
            "The automation event is outside the accepted replay window.",
            reason_code="automation_event_stale",
        )
    expected = hmac.new(
        _signing_secret_bytes(signing_secret),
        msg=timestamp_value.encode("ascii") + b"." + body,
        digestmod=hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected, match.group(1)):
        raise AutomationContractError(
            "The automation event signature is invalid.",
            reason_code="automation_event_signature_invalid",
        )
    try:
        raw = json.loads(body, object_pairs_hook=_reject_duplicate_keys)
        event = AutomationEventEnvelope.model_validate(raw)
    except (json.JSONDecodeError, ValidationError, AutomationContractError) as exc:
        raise AutomationContractError(
            "The automation event body is invalid.",
            reason_code="automation_event_body_invalid",
        ) from exc
    definition = _EVENT_BY_CODE.get(event.event_type)
    if definition is None or event.resource.type != definition.resource_type:
        raise AutomationContractError(
            "The automation event is not part of the approved contract.",
            reason_code="automation_event_contract_invalid",
        )
    unexpected = sorted(set(event.data) - definition.allowed_data_fields)
    if unexpected:
        raise AutomationContractError(
            "The automation event contains unapproved fields.",
            reason_code="automation_event_fields_not_approved",
        )
    _validate_minimized_value(event.data, path="data", depth=0)
    if normalized_headers.get("x-insightos-event-id") != event.event_id:
        raise AutomationContractError(
            "The automation event identity does not match its signed body.",
            reason_code="automation_event_identity_mismatch",
        )
    if normalized_headers.get("x-insightos-schema") != event.schema_version:
        raise AutomationContractError(
            "The automation event schema header does not match its signed body.",
            reason_code="automation_event_schema_mismatch",
        )
    return event


def _canonical_event_body(event: AutomationEventEnvelope) -> bytes:
    body = json.dumps(
        event.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    if len(body) > MAX_EVENT_BODY_BYTES:
        raise AutomationContractError(
            "The automation event is larger than the supported contract.",
            reason_code="automation_event_too_large",
        )
    return body


def _signing_secret_bytes(value: str) -> bytes:
    encoded = value.encode("utf-8")
    if len(encoded) < 32:
        raise AutomationContractError(
            "The automation signing secret is not strong enough.",
            reason_code="automation_signing_secret_invalid",
        )
    return encoded


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise AutomationContractError(
                "The automation event contains a duplicate field.",
                reason_code="automation_event_duplicate_field",
            )
        result[key] = value
    return result


def _validate_minimized_value(value: Any, *, path: str, depth: int) -> None:
    if depth > MAX_DATA_DEPTH:
        raise AutomationContractError(
            "The automation event data is nested too deeply.",
            reason_code="automation_event_data_too_deep",
        )
    if value is None or isinstance(value, bool | int):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise AutomationContractError(
                "The automation event contains an invalid number.",
                reason_code="automation_event_data_invalid",
            )
        return
    if isinstance(value, str):
        if len(value) > MAX_TEXT_LENGTH:
            raise AutomationContractError(
                "The automation event contains text that is too long.",
                reason_code="automation_event_data_too_large",
            )
        return
    if isinstance(value, list):
        if len(value) > MAX_COLLECTION_ITEMS:
            raise AutomationContractError(
                "The automation event contains too many items.",
                reason_code="automation_event_data_too_large",
            )
        for index, item in enumerate(value):
            _validate_minimized_value(item, path=f"{path}[{index}]", depth=depth + 1)
        return
    if isinstance(value, dict):
        if len(value) > MAX_COLLECTION_ITEMS:
            raise AutomationContractError(
                "The automation event contains too many fields.",
                reason_code="automation_event_data_too_large",
            )
        for key, item in value.items():
            normalized = str(key).lower()
            if not _KEY_PATTERN.fullmatch(normalized) or _is_forbidden_data_key(normalized):
                raise AutomationContractError(
                    "The automation event contains a field that cannot leave InsightOS.",
                    reason_code="automation_event_sensitive_field",
                )
            _validate_minimized_value(item, path=f"{path}.{normalized}", depth=depth + 1)
        return
    raise AutomationContractError(
        "The automation event contains an unsupported value.",
        reason_code="automation_event_data_invalid",
    )


def _is_forbidden_data_key(value: str) -> bool:
    return (
        value in _FORBIDDEN_DATA_KEYS
        or value.startswith("raw_")
        or value.startswith("provider_payload_")
        or value.endswith(_FORBIDDEN_KEY_SUFFIXES)
    )

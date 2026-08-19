from __future__ import annotations

import secrets
import hmac
import json
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.governed_ai_relay import GovernedAIRelayEnrollment
from app.models.governed_ai_relay_packet import (
    GovernedAIRelayDiagnosticAcknowledgement,
    GovernedAIRelayDiagnosticPacket,
)
from app.models.governed_ai_relay_qualification import (
    GovernedAIRelayModelQualification,
)
from app.models.governed_ai_relay_runtime import GovernedAIRelayRuntimeDiscovery
from app.models.organization import Organization
from app.services.audit_service import write_audit_log
from app.services.commercial_plan_service import (
    FEATURE_PRIVATE_AI_PROVIDER,
    require_commercial_feature,
)
from app.services.cost_economics_service import CostEconomicsError


PROTOCOL_VERSION = "outbound-local-relay-v1"
PACKET_PROTOCOL_VERSION = "outbound-local-relay-packet-v1"
DIAGNOSTIC_PACKET_KIND = "synthetic_connection_challenge"
ACTIVE_WINDOW = timedelta(minutes=5)
HEARTBEAT_WRITE_WINDOW = timedelta(seconds=30)
DIAGNOSTIC_PACKET_TTL = timedelta(minutes=5)
RUNTIME_DISCOVERY_FRESHNESS = timedelta(minutes=5)
RUNTIME_DISCOVERY_FUTURE_SKEW = timedelta(seconds=60)
LOCAL_MODEL_PROMPT_VERSION = "local-model-synthetic-v1"
REQUIRED_ACKNOWLEDGEMENTS = (
    "understands_connection_only",
    "understands_no_customer_prompts",
    "understands_no_database_or_execution_access",
    "understands_manual_revocation",
)


class GovernedAIRelayError(RuntimeError):
    def __init__(self, message: str, *, reason_code: str, status_code: int) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.status_code = status_code


def list_relay_enrollments(
    db: Session,
    *,
    organization_id: str,
    now: datetime | None = None,
) -> dict[str, object]:
    occurred_at = _as_utc(now or datetime.now(UTC))
    rows = (
        db.query(GovernedAIRelayEnrollment)
        .filter(GovernedAIRelayEnrollment.organization_id == organization_id)
        .order_by(
            GovernedAIRelayEnrollment.created_at.desc(),
            GovernedAIRelayEnrollment.id.desc(),
        )
        .all()
    )
    current = next((row for row in rows if row.status == "active"), None)
    return {
        "current": _serialize(current, now=occurred_at) if current else None,
        "history": [_serialize(row, now=occurred_at) for row in rows[:10]],
        "diagnostic": (
            _diagnostic_summary(db, enrollment_id=current.id, now=occurred_at)
            if current
            else None
        ),
        "runtime_discovery": (
            _runtime_discovery_summary(db, enrollment_id=current.id)
            if current
            else None
        ),
        "model_qualification": (
            _model_qualification_summary(db, enrollment_id=current.id)
            if current
            else None
        ),
        "protocol_version": PROTOCOL_VERSION,
        "truth": {
            "state": "connection_only",
            "summary": (
                "The relay can prove an outbound connection only. No customer "
                "prompts or work packets are available in this release."
            ),
        },
        "safety": _safety(),
    }


def create_relay_enrollment(
    db: Session,
    *,
    organization_id: str,
    actor_user_id: str,
    name: str,
    client_request_id: str,
    acknowledgements: dict[str, bool],
    now: datetime | None = None,
) -> dict[str, object]:
    require_commercial_feature(
        db,
        organization_id=organization_id,
        feature_code=FEATURE_PRIVATE_AI_PROVIDER,
    )
    organization = (
        db.query(Organization)
        .filter(Organization.id == organization_id)
        .with_for_update()
        .one_or_none()
    )
    if organization is None:
        raise GovernedAIRelayError(
            "Workspace not found.",
            reason_code="organization_not_found",
            status_code=404,
        )
    if organization.status != "active":
        raise GovernedAIRelayError(
            "This workspace cannot create a local relay connection right now.",
            reason_code="relay_workspace_unavailable",
            status_code=409,
        )
    normalized_name = name.strip()
    if len(normalized_name) < 2 or len(normalized_name) > 120:
        raise GovernedAIRelayError(
            "Enter a short name for this local relay.",
            reason_code="relay_name_invalid",
            status_code=422,
        )
    if not client_request_id.strip() or len(client_request_id.strip()) > 128:
        raise GovernedAIRelayError(
            "The relay request identifier is invalid.",
            reason_code="relay_request_invalid",
            status_code=422,
        )
    if any(acknowledgements.get(key) is not True for key in REQUIRED_ACKNOWLEDGEMENTS):
        raise GovernedAIRelayError(
            "Confirm every local relay safety statement before creating a connection key.",
            reason_code="relay_acknowledgements_required",
            status_code=422,
        )

    request_id_hash = _hash(f"{organization_id}:{client_request_id.strip()}")
    existing = (
        db.query(GovernedAIRelayEnrollment)
        .filter(
            GovernedAIRelayEnrollment.organization_id == organization_id,
            GovernedAIRelayEnrollment.request_id_hash == request_id_hash,
        )
        .one_or_none()
    )
    occurred_at = _as_utc(now or datetime.now(UTC))
    if existing is not None:
        return {
            "created": False,
            "enrollment_token": None,
            "item": _serialize(existing, now=occurred_at),
            "token_returned_once": True,
            "summary": (
                "This relay was already created. Rotate it with a new request if "
                "the one-time connection key was not saved."
            ),
            "safety": _safety(),
        }

    active_rows = (
        db.query(GovernedAIRelayEnrollment)
        .filter(
            GovernedAIRelayEnrollment.organization_id == organization_id,
            GovernedAIRelayEnrollment.status == "active",
        )
        .with_for_update()
        .all()
    )
    for row in active_rows:
        row.status = "revoked"
        row.revoked_by_user_id = actor_user_id
        row.revoked_at = occurred_at

    raw_token = f"iosr_{secrets.token_urlsafe(32)}"
    row = GovernedAIRelayEnrollment(
        tenant_id=organization_id,
        organization_id=organization_id,
        name=normalized_name,
        protocol_version=PROTOCOL_VERSION,
        token_hash=_hash(raw_token),
        token_hint=f"{raw_token[:10]}...",
        request_id_hash=request_id_hash,
        status="active",
        customer_prompts_allowed=False,
        decision_packets_enabled=False,
        database_access_allowed=False,
        execution_allowed=False,
        publishing_allowed=False,
        heartbeat_count=0,
        created_by_user_id=actor_user_id,
        created_at=occurred_at,
    )
    db.add(row)
    db.flush()
    write_audit_log(
        db,
        tenant_id=organization_id,
        actor_user_id=actor_user_id,
        event_type="ai.local_relay.enrolled",
        payload={
            "relay_enrollment_id": row.id,
            "protocol_version": PROTOCOL_VERSION,
            "connection_only": True,
            "customer_prompts_allowed": False,
            "execution_allowed": False,
        },
    )
    db.commit()
    db.refresh(row)
    return {
        "created": True,
        "enrollment_token": raw_token,
        "item": _serialize(row, now=occurred_at),
        "token_returned_once": True,
        "summary": "Save this connection key now. InsightOS will not show it again.",
        "safety": _safety(),
    }


def revoke_relay_enrollment(
    db: Session,
    *,
    organization_id: str,
    enrollment_id: str,
    actor_user_id: str,
    now: datetime | None = None,
) -> dict[str, object]:
    row = (
        db.query(GovernedAIRelayEnrollment)
        .filter(
            GovernedAIRelayEnrollment.id == enrollment_id,
            GovernedAIRelayEnrollment.organization_id == organization_id,
        )
        .with_for_update()
        .one_or_none()
    )
    if row is None:
        raise GovernedAIRelayError(
            "Local relay connection not found.",
            reason_code="relay_enrollment_not_found",
            status_code=404,
        )
    occurred_at = _as_utc(now or datetime.now(UTC))
    if row.status != "revoked":
        row.status = "revoked"
        row.revoked_by_user_id = actor_user_id
        row.revoked_at = occurred_at
        write_audit_log(
            db,
            tenant_id=organization_id,
            actor_user_id=actor_user_id,
            event_type="ai.local_relay.revoked",
            payload={"relay_enrollment_id": row.id},
        )
        db.commit()
        db.refresh(row)
    return {
        "revoked": True,
        "item": _serialize(row, now=occurred_at),
        "safety": _safety(),
    }


def create_relay_diagnostic_packet(
    db: Session,
    *,
    organization_id: str,
    enrollment_id: str,
    actor_user_id: str,
    client_request_id: str,
    now: datetime | None = None,
) -> dict[str, object]:
    require_commercial_feature(
        db,
        organization_id=organization_id,
        feature_code=FEATURE_PRIVATE_AI_PROVIDER,
    )
    enrollment = (
        db.query(GovernedAIRelayEnrollment)
        .filter(
            GovernedAIRelayEnrollment.id == enrollment_id,
            GovernedAIRelayEnrollment.organization_id == organization_id,
        )
        .with_for_update()
        .one_or_none()
    )
    if enrollment is None or enrollment.status != "active":
        raise GovernedAIRelayError(
            "Create an active local relay connection before preparing a diagnostic check.",
            reason_code="relay_enrollment_unavailable",
            status_code=409,
        )
    normalized_request_id = client_request_id.strip()
    if not normalized_request_id or len(normalized_request_id) > 128:
        raise GovernedAIRelayError(
            "The diagnostic request identifier is invalid.",
            reason_code="relay_diagnostic_request_invalid",
            status_code=422,
        )
    request_id_hash = _hash(
        f"{organization_id}:{enrollment_id}:{normalized_request_id}"
    )
    existing = (
        db.query(GovernedAIRelayDiagnosticPacket)
        .filter(
            GovernedAIRelayDiagnosticPacket.organization_id == organization_id,
            GovernedAIRelayDiagnosticPacket.enrollment_id == enrollment_id,
            GovernedAIRelayDiagnosticPacket.request_id_hash == request_id_hash,
        )
        .one_or_none()
    )
    occurred_at = _as_utc(now or datetime.now(UTC))
    if existing is not None:
        return {
            "created": False,
            "item": _serialize_diagnostic(db, existing, now=occurred_at),
            "safety": _diagnostic_safety(),
        }
    pending = _next_packet(db, enrollment_id=enrollment_id, now=occurred_at)
    if pending is not None:
        raise GovernedAIRelayError(
            "A synthetic relay check is already waiting. Let it finish or expire before creating another.",
            reason_code="relay_diagnostic_already_pending",
            status_code=409,
        )

    packet_id = str(uuid4())
    challenge = secrets.token_urlsafe(24)
    expires_at = occurred_at + DIAGNOSTIC_PACKET_TTL
    expected_response_hash = _diagnostic_response_hash(packet_id, challenge)
    artifact = {
        "id": packet_id,
        "organization_id": organization_id,
        "enrollment_id": enrollment_id,
        "protocol_version": PACKET_PROTOCOL_VERSION,
        "packet_kind": DIAGNOSTIC_PACKET_KIND,
        "challenge": challenge,
        "expected_response_hash": expected_response_hash,
        "created_at": occurred_at.isoformat(),
        "expires_at": expires_at.isoformat(),
        "safety": _diagnostic_safety(),
    }
    row = GovernedAIRelayDiagnosticPacket(
        id=packet_id,
        tenant_id=organization_id,
        organization_id=organization_id,
        enrollment_id=enrollment_id,
        protocol_version=PACKET_PROTOCOL_VERSION,
        packet_kind=DIAGNOSTIC_PACKET_KIND,
        challenge_nonce=challenge,
        expected_response_hash=expected_response_hash,
        artifact_hash=_hash_payload(artifact),
        request_id_hash=request_id_hash,
        customer_data_included=False,
        model_execution_requested=False,
        database_access_requested=False,
        business_execution_requested=False,
        publishing_requested=False,
        created_by_user_id=actor_user_id,
        created_at=occurred_at,
        expires_at=expires_at,
    )
    db.add(row)
    db.flush()
    write_audit_log(
        db,
        tenant_id=organization_id,
        actor_user_id=actor_user_id,
        event_type="ai.local_relay.synthetic_diagnostic_created",
        payload={
            "relay_enrollment_id": enrollment_id,
            "diagnostic_packet_id": row.id,
            "protocol_version": PACKET_PROTOCOL_VERSION,
            "customer_data_included": False,
            "model_execution_requested": False,
        },
    )
    db.commit()
    db.refresh(row)
    return {
        "created": True,
        "item": _serialize_diagnostic(db, row, now=occurred_at),
        "summary": "A short-lived synthetic connection check is waiting for the relay.",
        "safety": _diagnostic_safety(),
    }


def record_relay_heartbeat(
    db: Session,
    *,
    bearer_token: str,
    now: datetime | None = None,
) -> dict[str, object]:
    normalized_token = bearer_token.strip()
    row = _authorized_relay(db, bearer_token=normalized_token)

    occurred_at = _as_utc(now or datetime.now(UTC))
    previous_seen = _as_utc(row.last_seen_at) if row.last_seen_at else None
    duplicate = bool(
        previous_seen and occurred_at - previous_seen < HEARTBEAT_WRITE_WINDOW
    )
    if not duplicate:
        row.last_seen_at = occurred_at
        row.heartbeat_count += 1
    packet = _next_packet(db, enrollment_id=row.id, now=occurred_at)
    work = [
        _signed_diagnostic_packet(packet, bearer_token=normalized_token)
    ] if packet is not None else []
    db.commit()
    return {
        "accepted": True,
        "duplicate": duplicate,
        "protocol_version": PROTOCOL_VERSION,
        "connection_state": "connected",
        "next_check_after_seconds": 60,
        "work": work,
        "truth": {
            "state": "connection_only",
            "summary": (
                "Connection verified. Only a signed synthetic receipt check may "
                "appear; customer prompts and model work remain unavailable."
            ),
        },
        "safety": _safety(),
    }


def record_relay_runtime_discovery(
    db: Session,
    *,
    bearer_token: str,
    discovery_id: str,
    agent_version: str,
    runtime_kind: str,
    model_count: int,
    ollama_detected: bool,
    lm_studio_detected: bool,
    loopback_only: bool,
    customer_data_sent: bool,
    model_called: bool,
    model_identifiers_included: bool,
    observed_at: datetime,
    signature: str,
    now: datetime | None = None,
) -> dict[str, object]:
    normalized_token = bearer_token.strip()
    enrollment = _authorized_relay(db, bearer_token=normalized_token)
    occurred_at = _as_utc(now or datetime.now(UTC))
    if observed_at.tzinfo is None:
        raise GovernedAIRelayError(
            "The local software discovery timestamp must include a timezone.",
            reason_code="relay_runtime_discovery_timestamp_invalid",
            status_code=422,
        )
    normalized_observed_at = _as_utc(observed_at)
    if (
        normalized_observed_at < occurred_at - RUNTIME_DISCOVERY_FRESHNESS
        or normalized_observed_at > occurred_at + RUNTIME_DISCOVERY_FUTURE_SKEW
    ):
        raise GovernedAIRelayError(
            "The local software discovery report is outside its short validity window.",
            reason_code="relay_runtime_discovery_stale",
            status_code=422,
        )
    try:
        normalized_id = str(UUID(discovery_id))
    except (ValueError, AttributeError, TypeError) as exc:
        raise GovernedAIRelayError(
            "The local software discovery identifier is invalid.",
            reason_code="relay_runtime_discovery_id_invalid",
            status_code=422,
        ) from exc
    if not 1 <= len(agent_version.strip()) <= 30:
        raise GovernedAIRelayError(
            "The local relay version is invalid.",
            reason_code="relay_runtime_agent_version_invalid",
            status_code=422,
        )
    expected_runtime_kind = _runtime_kind(
        ollama_detected=ollama_detected,
        lm_studio_detected=lm_studio_detected,
    )
    if (
        runtime_kind != expected_runtime_kind
        or not 0 <= model_count <= 1000
        or (runtime_kind == "not_found" and model_count != 0)
        or loopback_only is not True
        or customer_data_sent is not False
        or model_called is not False
        or model_identifiers_included is not False
    ):
        raise GovernedAIRelayError(
            "The local software discovery report did not match its safety boundary.",
            reason_code="relay_runtime_discovery_invalid",
            status_code=422,
        )
    payload = {
        "discovery_id": normalized_id,
        "agent_version": agent_version.strip(),
        "runtime_kind": runtime_kind,
        "model_count": model_count,
        "ollama_detected": ollama_detected,
        "lm_studio_detected": lm_studio_detected,
        "loopback_only": True,
        "customer_data_sent": False,
        "model_called": False,
        "model_identifiers_included": False,
        "observed_at": normalized_observed_at.isoformat(),
    }
    normalized_signature = signature.strip().lower()
    if not secrets.compare_digest(_sign(normalized_token, payload), normalized_signature):
        raise GovernedAIRelayError(
            "The local software discovery signature is invalid.",
            reason_code="relay_runtime_discovery_signature_invalid",
            status_code=401,
        )
    artifact_hash = _hash_payload(payload)
    existing = db.get(GovernedAIRelayRuntimeDiscovery, normalized_id)
    if existing is not None:
        if (
            existing.enrollment_id != enrollment.id
            or not secrets.compare_digest(existing.artifact_hash, artifact_hash)
        ):
            raise GovernedAIRelayError(
                "This local software discovery identifier was already used for different evidence.",
                reason_code="relay_runtime_discovery_conflict",
                status_code=409,
            )
        return _runtime_discovery_result(existing, created=False)
    row = GovernedAIRelayRuntimeDiscovery(
        id=normalized_id,
        tenant_id=enrollment.organization_id,
        organization_id=enrollment.organization_id,
        enrollment_id=enrollment.id,
        agent_version=agent_version.strip(),
        runtime_kind=runtime_kind,
        model_count=model_count,
        ollama_detected=ollama_detected,
        lm_studio_detected=lm_studio_detected,
        loopback_only=True,
        customer_data_sent=False,
        model_called=False,
        model_identifiers_included=False,
        request_signature_hash=_hash(normalized_signature),
        artifact_hash=artifact_hash,
        observed_at=normalized_observed_at,
        received_at=occurred_at,
    )
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
    except IntegrityError:
        existing = db.get(GovernedAIRelayRuntimeDiscovery, normalized_id)
        if existing is None or existing.artifact_hash != artifact_hash:
            raise GovernedAIRelayError(
                "This local software discovery identifier was already used for different evidence.",
                reason_code="relay_runtime_discovery_conflict",
                status_code=409,
            )
        return _runtime_discovery_result(existing, created=False)
    write_audit_log(
        db,
        tenant_id=enrollment.organization_id,
        actor_user_id=None,
        event_type="ai.local_relay.runtime_discovered",
        payload={
            "relay_enrollment_id": enrollment.id,
            "runtime_kind": runtime_kind,
            "model_count": model_count,
            "loopback_only": True,
            "customer_data_sent": False,
            "model_called": False,
            "model_identifiers_included": False,
        },
    )
    db.commit()
    db.refresh(row)
    return _runtime_discovery_result(row, created=True)


def record_relay_model_qualification(
    db: Session,
    *,
    bearer_token: str,
    qualification_id: str,
    agent_version: str,
    runtime_kind: str,
    local_model_fingerprint: str,
    prompt_version: str,
    status: str,
    latency_ms: int,
    output_json_valid: bool,
    required_contract_matched: bool,
    synthetic_input_only: bool,
    model_call_attempted: bool,
    model_response_received: bool,
    customer_data_sent: bool,
    raw_model_identifier_sent: bool,
    model_output_sent: bool,
    customer_work_allowed: bool,
    publishing_allowed: bool,
    observed_at: datetime,
    signature: str,
    now: datetime | None = None,
) -> dict[str, object]:
    normalized_token = bearer_token.strip()
    enrollment = _authorized_relay(db, bearer_token=normalized_token)
    occurred_at = _as_utc(now or datetime.now(UTC))
    if observed_at.tzinfo is None:
        raise GovernedAIRelayError(
            "The synthetic model check timestamp must include a timezone.",
            reason_code="relay_model_qualification_timestamp_invalid",
            status_code=422,
        )
    normalized_observed_at = _as_utc(observed_at)
    if (
        normalized_observed_at < occurred_at - RUNTIME_DISCOVERY_FRESHNESS
        or normalized_observed_at > occurred_at + RUNTIME_DISCOVERY_FUTURE_SKEW
    ):
        raise GovernedAIRelayError(
            "The synthetic model check is outside its short validity window.",
            reason_code="relay_model_qualification_stale",
            status_code=422,
        )
    try:
        normalized_id = str(UUID(qualification_id))
    except (ValueError, AttributeError, TypeError) as exc:
        raise GovernedAIRelayError(
            "The synthetic model check identifier is invalid.",
            reason_code="relay_model_qualification_id_invalid",
            status_code=422,
        ) from exc
    normalized_fingerprint = local_model_fingerprint.strip().lower()
    valid_fingerprint = len(normalized_fingerprint) == 64 and all(
        char in "0123456789abcdef" for char in normalized_fingerprint
    )
    safety_valid = (
        synthetic_input_only is True
        and model_call_attempted is True
        and customer_data_sent is False
        and raw_model_identifier_sent is False
        and model_output_sent is False
        and customer_work_allowed is False
        and publishing_allowed is False
    )
    contract_valid = (
        runtime_kind in {"ollama", "lm_studio"}
        and prompt_version == LOCAL_MODEL_PROMPT_VERSION
        and status in {"passed", "failed"}
        and 0 <= latency_ms <= 120000
        and valid_fingerprint
        and 1 <= len(agent_version.strip()) <= 30
        and (
            status == "failed"
            or (
                model_response_received
                and output_json_valid
                and required_contract_matched
            )
        )
    )
    if not safety_valid or not contract_valid:
        raise GovernedAIRelayError(
            "The synthetic model check did not match its fixed safety contract.",
            reason_code="relay_model_qualification_invalid",
            status_code=422,
        )
    payload = {
        "qualification_id": normalized_id,
        "agent_version": agent_version.strip(),
        "runtime_kind": runtime_kind,
        "local_model_fingerprint": normalized_fingerprint,
        "prompt_version": prompt_version,
        "status": status,
        "latency_ms": latency_ms,
        "output_json_valid": output_json_valid,
        "required_contract_matched": required_contract_matched,
        "synthetic_input_only": True,
        "model_call_attempted": True,
        "model_response_received": model_response_received,
        "customer_data_sent": False,
        "raw_model_identifier_sent": False,
        "model_output_sent": False,
        "customer_work_allowed": False,
        "publishing_allowed": False,
        "observed_at": normalized_observed_at.isoformat(),
    }
    normalized_signature = signature.strip().lower()
    if not secrets.compare_digest(_sign(normalized_token, payload), normalized_signature):
        raise GovernedAIRelayError(
            "The synthetic model check signature is invalid.",
            reason_code="relay_model_qualification_signature_invalid",
            status_code=401,
        )
    artifact_hash = _hash_payload(payload)
    existing = db.get(GovernedAIRelayModelQualification, normalized_id)
    if existing is not None:
        if (
            existing.enrollment_id != enrollment.id
            or not secrets.compare_digest(existing.artifact_hash, artifact_hash)
        ):
            raise GovernedAIRelayError(
                "This synthetic model check identifier was already used for different evidence.",
                reason_code="relay_model_qualification_conflict",
                status_code=409,
            )
        return _model_qualification_result(existing, created=False)
    row = GovernedAIRelayModelQualification(
        id=normalized_id,
        tenant_id=enrollment.organization_id,
        organization_id=enrollment.organization_id,
        enrollment_id=enrollment.id,
        agent_version=agent_version.strip(),
        runtime_kind=runtime_kind,
        local_model_fingerprint=normalized_fingerprint,
        prompt_version=prompt_version,
        status=status,
        latency_ms=latency_ms,
        output_json_valid=output_json_valid,
        required_contract_matched=required_contract_matched,
        synthetic_input_only=True,
        model_call_attempted=True,
        model_response_received=model_response_received,
        customer_data_sent=False,
        raw_model_identifier_sent=False,
        model_output_sent=False,
        customer_work_allowed=False,
        publishing_allowed=False,
        request_signature_hash=_hash(normalized_signature),
        artifact_hash=artifact_hash,
        observed_at=normalized_observed_at,
        received_at=occurred_at,
    )
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
    except IntegrityError:
        existing = db.get(GovernedAIRelayModelQualification, normalized_id)
        if existing is None or existing.artifact_hash != artifact_hash:
            raise GovernedAIRelayError(
                "This synthetic model check identifier was already used for different evidence.",
                reason_code="relay_model_qualification_conflict",
                status_code=409,
            )
        return _model_qualification_result(existing, created=False)
    write_audit_log(
        db,
        tenant_id=enrollment.organization_id,
        actor_user_id=None,
        event_type="ai.local_relay.model_qualified",
        payload={
            "relay_enrollment_id": enrollment.id,
            "runtime_kind": runtime_kind,
            "status": status,
            "latency_ms": latency_ms,
            "synthetic_input_only": True,
            "model_call_attempted": True,
            "model_response_received": model_response_received,
            "customer_data_sent": False,
            "raw_model_identifier_sent": False,
            "model_output_sent": False,
            "customer_work_allowed": False,
            "publishing_allowed": False,
        },
    )
    db.commit()
    db.refresh(row)
    return _model_qualification_result(row, created=True)


def acknowledge_relay_diagnostic_packet(
    db: Session,
    *,
    bearer_token: str,
    packet_id: str,
    packet_artifact_hash: str,
    response_hash: str,
    signature: str,
    now: datetime | None = None,
) -> dict[str, object]:
    normalized_token = bearer_token.strip()
    enrollment = _authorized_relay(db, bearer_token=normalized_token)
    packet = (
        db.query(GovernedAIRelayDiagnosticPacket)
        .filter(
            GovernedAIRelayDiagnosticPacket.id == packet_id,
            GovernedAIRelayDiagnosticPacket.enrollment_id == enrollment.id,
            GovernedAIRelayDiagnosticPacket.organization_id
            == enrollment.organization_id,
        )
        .one_or_none()
    )
    if packet is None:
        raise GovernedAIRelayError(
            "The synthetic relay check was not found for this connection.",
            reason_code="relay_diagnostic_not_found",
            status_code=404,
        )
    occurred_at = _as_utc(now or datetime.now(UTC))
    normalized_artifact_hash = packet_artifact_hash.strip().lower()
    normalized_response_hash = response_hash.strip().lower()
    normalized_signature = signature.strip().lower()
    if not secrets.compare_digest(packet.artifact_hash, normalized_artifact_hash):
        raise GovernedAIRelayError(
            "The synthetic relay check no longer matches the issued packet.",
            reason_code="relay_diagnostic_artifact_mismatch",
            status_code=409,
        )
    if not secrets.compare_digest(packet.expected_response_hash, normalized_response_hash):
        raise GovernedAIRelayError(
            "The synthetic relay response did not match the exact receipt challenge.",
            reason_code="relay_diagnostic_response_invalid",
            status_code=422,
        )
    expected_signature = _sign(
        normalized_token,
        _ack_signature_payload(
            packet_id=packet.id,
            packet_artifact_hash=packet.artifact_hash,
            response_hash=normalized_response_hash,
        ),
    )
    if not secrets.compare_digest(expected_signature, normalized_signature):
        raise GovernedAIRelayError(
            "The synthetic relay acknowledgement signature is invalid.",
            reason_code="relay_diagnostic_signature_invalid",
            status_code=401,
        )

    existing = (
        db.query(GovernedAIRelayDiagnosticAcknowledgement)
        .filter(GovernedAIRelayDiagnosticAcknowledgement.packet_id == packet.id)
        .one_or_none()
    )
    if existing is not None:
        return _acknowledgement_result(existing, created=False)
    if occurred_at >= _as_utc(packet.expires_at):
        raise GovernedAIRelayError(
            "This synthetic relay check expired. Prepare a new check.",
            reason_code="relay_diagnostic_expired",
            status_code=410,
        )
    ack_artifact = {
        "packet_id": packet.id,
        "enrollment_id": enrollment.id,
        "packet_artifact_hash": packet.artifact_hash,
        "response_hash": normalized_response_hash,
        "acknowledged_at": occurred_at.isoformat(),
        "safety": _acknowledgement_safety(),
    }
    row = GovernedAIRelayDiagnosticAcknowledgement(
        tenant_id=enrollment.organization_id,
        organization_id=enrollment.organization_id,
        enrollment_id=enrollment.id,
        packet_id=packet.id,
        response_hash=normalized_response_hash,
        request_signature_hash=_hash(normalized_signature),
        packet_artifact_hash=packet.artifact_hash,
        artifact_hash=_hash_payload(ack_artifact),
        customer_data_processed=False,
        model_called=False,
        database_accessed=False,
        business_work_executed=False,
        publishing_performed=False,
        acknowledged_at=occurred_at,
    )
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
    except IntegrityError:
        existing = (
            db.query(GovernedAIRelayDiagnosticAcknowledgement)
            .filter(GovernedAIRelayDiagnosticAcknowledgement.packet_id == packet.id)
            .one()
        )
        return _acknowledgement_result(existing, created=False)
    write_audit_log(
        db,
        tenant_id=enrollment.organization_id,
        actor_user_id=None,
        event_type="ai.local_relay.synthetic_diagnostic_acknowledged",
        payload={
            "relay_enrollment_id": enrollment.id,
            "diagnostic_packet_id": packet.id,
            "customer_data_processed": False,
            "model_called": False,
        },
    )
    db.commit()
    db.refresh(row)
    return _acknowledgement_result(row, created=True)


def _authorized_relay(
    db: Session,
    *,
    bearer_token: str,
) -> GovernedAIRelayEnrollment:
    supplied_hash = _hash(bearer_token)
    row = (
        db.query(GovernedAIRelayEnrollment)
        .filter(GovernedAIRelayEnrollment.token_hash == supplied_hash)
        .one_or_none()
    )
    if (
        row is None
        or not secrets.compare_digest(row.token_hash, supplied_hash)
        or row.status != "active"
    ):
        raise GovernedAIRelayError(
            "The local relay connection key is invalid or revoked.",
            reason_code="relay_token_invalid",
            status_code=401,
        )
    try:
        require_commercial_feature(
            db,
            organization_id=row.organization_id,
            feature_code=FEATURE_PRIVATE_AI_PROVIDER,
        )
    except CostEconomicsError as exc:
        raise GovernedAIRelayError(
            "This local relay connection is not available on the current plan.",
            reason_code="relay_plan_unavailable",
            status_code=403,
        ) from exc
    locked = (
        db.query(GovernedAIRelayEnrollment)
        .filter(
            GovernedAIRelayEnrollment.id == row.id,
            GovernedAIRelayEnrollment.token_hash == supplied_hash,
        )
        .populate_existing()
        .with_for_update()
        .one_or_none()
    )
    if locked is None or locked.status != "active":
        raise GovernedAIRelayError(
            "The local relay connection key is invalid or revoked.",
            reason_code="relay_token_invalid",
            status_code=401,
        )
    organization = db.get(Organization, locked.organization_id)
    if organization is None or organization.status != "active":
        raise GovernedAIRelayError(
            "This local relay connection is not available.",
            reason_code="relay_workspace_unavailable",
            status_code=403,
        )
    return locked


def _next_packet(
    db: Session,
    *,
    enrollment_id: str,
    now: datetime,
) -> GovernedAIRelayDiagnosticPacket | None:
    acknowledgement_exists = (
        select(GovernedAIRelayDiagnosticAcknowledgement.id)
        .where(
            GovernedAIRelayDiagnosticAcknowledgement.packet_id
            == GovernedAIRelayDiagnosticPacket.id
        )
        .exists()
    )
    return (
        db.query(GovernedAIRelayDiagnosticPacket)
        .filter(
            GovernedAIRelayDiagnosticPacket.enrollment_id == enrollment_id,
            GovernedAIRelayDiagnosticPacket.expires_at > now,
            ~acknowledgement_exists,
        )
        .order_by(
            GovernedAIRelayDiagnosticPacket.created_at.asc(),
            GovernedAIRelayDiagnosticPacket.id.asc(),
        )
        .first()
    )


def _signed_diagnostic_packet(
    packet: GovernedAIRelayDiagnosticPacket,
    *,
    bearer_token: str,
) -> dict[str, object]:
    body: dict[str, object] = {
        "id": packet.id,
        "kind": packet.packet_kind,
        "protocol_version": packet.protocol_version,
        "issued_at": _as_utc(packet.created_at).isoformat(),
        "expires_at": _as_utc(packet.expires_at).isoformat(),
        "artifact_hash": packet.artifact_hash,
        "payload": {
            "challenge": packet.challenge_nonce,
            "expected_action": "acknowledge_synthetic_receipt",
            "response_hash_input": f"{packet.id}:<challenge>:received",
        },
        "safety": _diagnostic_safety(),
    }
    return {
        **body,
        "signature_algorithm": "hmac-sha256",
        "signature": _sign(bearer_token, body),
        "acknowledge_path": f"/api/v1/ai/relay/packets/{packet.id}/acknowledge",
    }


def _diagnostic_summary(
    db: Session,
    *,
    enrollment_id: str,
    now: datetime,
) -> dict[str, object] | None:
    row = (
        db.query(GovernedAIRelayDiagnosticPacket)
        .filter(GovernedAIRelayDiagnosticPacket.enrollment_id == enrollment_id)
        .order_by(
            GovernedAIRelayDiagnosticPacket.created_at.desc(),
            GovernedAIRelayDiagnosticPacket.id.desc(),
        )
        .first()
    )
    return _serialize_diagnostic(db, row, now=now) if row is not None else None


def _runtime_discovery_summary(
    db: Session,
    *,
    enrollment_id: str,
) -> dict[str, object] | None:
    row = (
        db.query(GovernedAIRelayRuntimeDiscovery)
        .filter(GovernedAIRelayRuntimeDiscovery.enrollment_id == enrollment_id)
        .order_by(
            GovernedAIRelayRuntimeDiscovery.received_at.desc(),
            GovernedAIRelayRuntimeDiscovery.id.desc(),
        )
        .first()
    )
    return _serialize_runtime_discovery(row) if row is not None else None


def _model_qualification_summary(
    db: Session,
    *,
    enrollment_id: str,
) -> dict[str, object] | None:
    row = (
        db.query(GovernedAIRelayModelQualification)
        .filter(GovernedAIRelayModelQualification.enrollment_id == enrollment_id)
        .order_by(
            GovernedAIRelayModelQualification.received_at.desc(),
            GovernedAIRelayModelQualification.id.desc(),
        )
        .first()
    )
    return _serialize_model_qualification(row) if row is not None else None


def _runtime_kind(*, ollama_detected: bool, lm_studio_detected: bool) -> str:
    if ollama_detected and lm_studio_detected:
        return "multiple"
    if ollama_detected:
        return "ollama"
    if lm_studio_detected:
        return "lm_studio"
    return "not_found"


def _serialize_runtime_discovery(
    row: GovernedAIRelayRuntimeDiscovery,
) -> dict[str, object]:
    return {
        "id": row.id,
        "agent_version": row.agent_version,
        "runtime_kind": row.runtime_kind,
        "model_count": row.model_count,
        "ollama_detected": row.ollama_detected,
        "lm_studio_detected": row.lm_studio_detected,
        "observed_at": _as_utc(row.observed_at).isoformat(),
        "received_at": _as_utc(row.received_at).isoformat(),
        "loopback_only": True,
        "customer_data_sent": False,
        "model_called": False,
        "model_identifiers_included": False,
        "truth": {
            "state": "discovery_only",
            "summary": (
                "The relay checked supported software on this computer only. "
                "Model names stayed on the computer, and no model was called."
            ),
        },
    }


def _runtime_discovery_result(
    row: GovernedAIRelayRuntimeDiscovery,
    *,
    created: bool,
) -> dict[str, object]:
    return {
        "accepted": True,
        "created": created,
        "item": _serialize_runtime_discovery(row),
    }


def _serialize_model_qualification(
    row: GovernedAIRelayModelQualification,
) -> dict[str, object]:
    return {
        "id": row.id,
        "agent_version": row.agent_version,
        "runtime_kind": row.runtime_kind,
        "prompt_version": row.prompt_version,
        "status": row.status,
        "latency_ms": row.latency_ms,
        "output_json_valid": row.output_json_valid,
        "required_contract_matched": row.required_contract_matched,
        "observed_at": _as_utc(row.observed_at).isoformat(),
        "received_at": _as_utc(row.received_at).isoformat(),
        "synthetic_input_only": True,
        "model_call_attempted": True,
        "model_response_received": row.model_response_received,
        "customer_data_sent": False,
        "raw_model_identifier_sent": False,
        "model_output_sent": False,
        "customer_work_allowed": False,
        "publishing_allowed": False,
        "truth": {
            "state": "qualification_only",
            "summary": (
                "One local model received a fixed made-up check. Its name and "
                "response stayed on the computer, and this result enables no work."
            ),
        },
    }


def _model_qualification_result(
    row: GovernedAIRelayModelQualification,
    *,
    created: bool,
) -> dict[str, object]:
    return {
        "accepted": True,
        "created": created,
        "item": _serialize_model_qualification(row),
    }


def _serialize_diagnostic(
    db: Session,
    row: GovernedAIRelayDiagnosticPacket,
    *,
    now: datetime,
) -> dict[str, object]:
    acknowledgement = (
        db.query(GovernedAIRelayDiagnosticAcknowledgement)
        .filter(GovernedAIRelayDiagnosticAcknowledgement.packet_id == row.id)
        .one_or_none()
    )
    if acknowledgement is not None:
        state = "verified"
    elif now >= _as_utc(row.expires_at):
        state = "expired"
    else:
        state = "waiting_for_relay"
    return {
        "id": row.id,
        "protocol_version": row.protocol_version,
        "kind": row.packet_kind,
        "state": state,
        "created_at": _as_utc(row.created_at).isoformat(),
        "expires_at": _as_utc(row.expires_at).isoformat(),
        "acknowledged_at": (
            _as_utc(acknowledgement.acknowledged_at).isoformat()
            if acknowledgement is not None
            else None
        ),
        "synthetic_only": True,
        **_diagnostic_safety(),
    }


def _acknowledgement_result(
    row: GovernedAIRelayDiagnosticAcknowledgement,
    *,
    created: bool,
) -> dict[str, object]:
    return {
        "accepted": True,
        "created": created,
        "packet_id": row.packet_id,
        "state": "verified",
        "acknowledged_at": _as_utc(row.acknowledged_at).isoformat(),
        "safety": _acknowledgement_safety(),
    }


def _diagnostic_safety() -> dict[str, bool]:
    return {
        "customer_data_included": False,
        "model_execution_requested": False,
        "database_access_requested": False,
        "business_execution_requested": False,
        "publishing_requested": False,
    }


def _acknowledgement_safety() -> dict[str, bool]:
    return {
        "customer_data_processed": False,
        "model_called": False,
        "database_accessed": False,
        "business_work_executed": False,
        "publishing_performed": False,
    }


def _diagnostic_response_hash(packet_id: str, challenge: str) -> str:
    return _hash(f"{packet_id}:{challenge}:received")


def _ack_signature_payload(
    *,
    packet_id: str,
    packet_artifact_hash: str,
    response_hash: str,
) -> dict[str, str]:
    return {
        "packet_id": packet_id,
        "packet_artifact_hash": packet_artifact_hash,
        "response_hash": response_hash,
    }


def _sign(secret: str, payload: dict[str, object]) -> str:
    return hmac.new(
        secret.encode("utf-8"),
        _canonical_json(payload).encode("utf-8"),
        sha256,
    ).hexdigest()


def _hash_payload(payload: dict[str, object]) -> str:
    return _hash(_canonical_json(payload))


def _canonical_json(payload: dict[str, object]) -> str:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def _serialize(
    row: GovernedAIRelayEnrollment,
    *,
    now: datetime,
) -> dict[str, object]:
    last_seen = _as_utc(row.last_seen_at) if row.last_seen_at else None
    if row.status == "revoked":
        state = "revoked"
    elif last_seen is None:
        state = "waiting_for_first_check"
    elif now - last_seen <= ACTIVE_WINDOW:
        state = "connected"
    else:
        state = "needs_reconnect"
    return {
        "id": row.id,
        "name": row.name,
        "protocol_version": row.protocol_version,
        "status": row.status,
        "connection_state": state,
        "token_hint": row.token_hint,
        "heartbeat_count": row.heartbeat_count,
        "last_seen_at": last_seen.isoformat() if last_seen else None,
        "created_at": _as_utc(row.created_at).isoformat(),
        "revoked_at": _as_utc(row.revoked_at).isoformat() if row.revoked_at else None,
        **_safety(),
    }


def _safety() -> dict[str, bool]:
    return {
        "customer_prompts_allowed": False,
        "decision_packets_enabled": False,
        "database_access_allowed": False,
        "execution_allowed": False,
        "publishing_allowed": False,
    }


def _hash(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)

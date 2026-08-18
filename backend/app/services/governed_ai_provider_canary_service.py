from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
from typing import Any

from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.governed_ai_provider_canary import (
    GovernedAIProviderCanaryAttempt,
    GovernedAIProviderCanaryEvent,
    GovernedAIProviderCanaryHealthSnapshot,
)
from app.models.governed_ai_provider_capability import (
    GovernedAIProviderCapabilityAttempt,
)
from app.models.governed_ai_provider_connection import GovernedAIProviderConnection
from app.models.governed_ai_provider_routing_readiness import (
    GovernedAIProviderRoutingReadiness,
)
from app.models.organization import Organization
from app.services.audit_service import write_audit_log
from app.services.cost_economics_service import CostEconomicsError
from app.services.commercial_plan_service import (
    FEATURE_PRIVATE_AI_PROVIDER,
    require_commercial_feature,
)
from app.services.governed_ai_provider_connection_service import (
    GovernedAIProviderConnectionError,
)
from app.services.governed_ai_provider_standby_service import (
    current_provider_standby_event,
)


CANARY_FEATURE = "intelligence_brief"
CANARY_TRAFFIC_PERCENTAGE = 5
CANARY_DAILY_PROMPT_LIMIT = 1
CANARY_MONITORING_WINDOW_DAYS = 30
CANARY_REQUIRED_SUCCESS_DAYS = 3
CANARY_MAX_LATENCY_MS = 8000
_READINESS_MAX_AGE = timedelta(hours=24)
_ACKS = (
    "reviewed_five_percent_limit",
    "understands_real_customer_prompt",
    "understands_managed_fallback_required",
    "understands_automatic_rollback",
    "understands_no_automatic_changes",
)


@dataclass(frozen=True)
class CanarySelection:
    event_id: str
    connection_id: str
    model_identifier: str


def list_provider_canary(
    db: Session,
    *,
    organization_id: str,
    connection_id: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    occurred_at = _as_utc(now or datetime.now(UTC))
    connection = _connection(db, organization_id=organization_id, connection_id=connection_id)
    current = _latest_event(db, organization_id=organization_id)
    recorded_here = bool(
        current
        and current.action == "enabled"
        and current.connection_id == connection_id
    )
    active_here = bool(
        recorded_here
        and _event_evidence_current(
            db,
            event=current,
            connection=connection,
            now=occurred_at,
        )
    )
    active_elsewhere = bool(
        current
        and current.action == "enabled"
        and current.connection_id != connection_id
    )
    attempts = _usage(db, organization_id=organization_id, now=occurred_at)
    state = (
        "canary"
        if active_here
        else "needs_attention"
        if recorded_here
        else "canary_elsewhere"
        if active_elsewhere
        else "inactive"
    )
    return {
        "current": _serialize_event(current) if current else None,
        "state": state,
        "routing_enabled": active_here,
        "feature": CANARY_FEATURE,
        "traffic_percentage": CANARY_TRAFFIC_PERCENTAGE if active_here else 0,
        "max_prompts_per_day": CANARY_DAILY_PROMPT_LIMIT,
        "customer_prompts_allowed": active_here,
        "automatic_rollback_enabled": True,
        "automatic_changes_allowed": False,
        "automatic_activation_allowed": False,
        "usage": attempts,
        "truth": {
            "state": state,
            "summary": (
                "A fixed 5% canary is available for the daily explanation, with at most one private-AI prompt per day and immediate managed fallback."
                if active_here
                else "Private AI is not receiving customer prompts from this connection."
            ),
        },
    }


def list_canary_monitoring(
    db: Session,
    *,
    organization_id: str,
    connection_id: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    occurred_at = _as_utc(now or datetime.now(UTC))
    connection = _connection(
        db,
        organization_id=organization_id,
        connection_id=connection_id,
    )
    evidence = _monitoring_evidence(
        db,
        organization_id=organization_id,
        connection=connection,
        now=occurred_at,
    )
    latest = (
        db.query(GovernedAIProviderCanaryHealthSnapshot)
        .filter(
            GovernedAIProviderCanaryHealthSnapshot.organization_id == organization_id,
            GovernedAIProviderCanaryHealthSnapshot.connection_id == connection_id,
        )
        .order_by(
            GovernedAIProviderCanaryHealthSnapshot.created_at.desc(),
            GovernedAIProviderCanaryHealthSnapshot.id.desc(),
        )
        .first()
    )
    return {
        "state": evidence["status"],
        "latest": _serialize_health(latest) if latest else None,
        "evidence": evidence,
        "traffic_change_allowed": False,
        "capability_change_allowed": False,
        "automatic_activation_allowed": False,
        "automatic_changes_allowed": False,
        "truth": {
            "state": evidence["status"],
            "summary": _monitoring_summary(evidence["status"]),
        },
    }


def create_canary_monitoring_snapshot(
    db: Session,
    *,
    organization_id: str,
    connection_id: str,
    actor_user_id: str,
    client_request_id: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    require_commercial_feature(
        db,
        organization_id=organization_id,
        feature_code=FEATURE_PRIVATE_AI_PROVIDER,
    )
    request_id = client_request_id.strip()
    if len(request_id) < 8 or len(request_id) > 64:
        raise _error(
            "The request identifier is invalid.",
            "ai_provider_canary_monitoring_request_invalid",
            422,
        )
    occurred_at = _as_utc(now or datetime.now(UTC))
    organization = (
        db.query(Organization)
        .filter(Organization.id == organization_id)
        .populate_existing()
        .with_for_update()
        .one_or_none()
    )
    if organization is None:
        raise _error("Organization not found.", "organization_not_found", 404)
    connection = _connection(
        db,
        organization_id=organization_id,
        connection_id=connection_id,
    )
    idempotency_key = _hash(
        {
            "organization_id": organization_id,
            "request_id": request_id,
            "kind": "canary_health_snapshot",
        }
    )
    existing = (
        db.query(GovernedAIProviderCanaryHealthSnapshot)
        .filter(
            GovernedAIProviderCanaryHealthSnapshot.organization_id == organization_id,
            GovernedAIProviderCanaryHealthSnapshot.idempotency_key == idempotency_key,
        )
        .one_or_none()
    )
    if existing is not None:
        if existing.connection_id != connection_id:
            raise _error(
                "This request identifier was already used differently.",
                "ai_provider_canary_monitoring_request_conflict",
                409,
            )
        return {
            "created": False,
            "item": _serialize_health(existing),
            **list_canary_monitoring(
                db,
                organization_id=organization_id,
                connection_id=connection_id,
                now=occurred_at,
            ),
        }

    canary_event = _latest_enabled_event(
        db,
        organization_id=organization_id,
        connection_id=connection_id,
    )
    if canary_event is None:
        raise _error(
            "Start the fixed private-AI check before saving a monitoring review.",
            "ai_provider_canary_monitoring_history_required",
            409,
        )
    evidence = _monitoring_evidence(
        db,
        organization_id=organization_id,
        connection=connection,
        now=occurred_at,
    )
    artifact = {
        "connection_id": connection_id,
        "canary_event_id": canary_event.id,
        **evidence,
        "traffic_change_allowed": False,
        "capability_change_allowed": False,
        "automatic_activation_allowed": False,
        "automatic_changes_allowed": False,
    }
    row = GovernedAIProviderCanaryHealthSnapshot(
        tenant_id=organization_id,
        organization_id=organization_id,
        connection_id=connection_id,
        canary_event_id=canary_event.id,
        feature=CANARY_FEATURE,
        status=evidence["status"],
        window_days=CANARY_MONITORING_WINDOW_DAYS,
        required_success_days=CANARY_REQUIRED_SUCCESS_DAYS,
        max_latency_threshold_ms=CANARY_MAX_LATENCY_MS,
        private_successes=evidence["private_successes"],
        distinct_success_days=evidence["distinct_success_days"],
        managed_fallbacks=evidence["managed_fallbacks"],
        automatic_rollbacks=evidence["automatic_rollbacks"],
        max_latency_ms=evidence["max_latency_ms"],
        blockers=evidence["blockers"],
        traffic_change_allowed=False,
        capability_change_allowed=False,
        automatic_activation_allowed=False,
        automatic_changes_allowed=False,
        artifact_hash=_hash(artifact),
        idempotency_key=idempotency_key,
        created_by_user_id=actor_user_id,
        created_at=occurred_at,
    )
    db.add(row)
    write_audit_log(
        db,
        tenant_id=organization_id,
        actor_user_id=actor_user_id,
        event_type="ai.provider_canary.monitoring_snapshot_created",
        payload={
            "connection_id": connection_id,
            "canary_event_id": canary_event.id,
            "health_snapshot_id": row.id,
            "status": row.status,
            "private_successes": row.private_successes,
            "distinct_success_days": row.distinct_success_days,
            "managed_fallbacks": row.managed_fallbacks,
            "automatic_rollbacks": row.automatic_rollbacks,
            "max_latency_ms": row.max_latency_ms,
            "traffic_change_allowed": False,
            "capability_change_allowed": False,
        },
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        repeated = (
            db.query(GovernedAIProviderCanaryHealthSnapshot)
            .filter(
                GovernedAIProviderCanaryHealthSnapshot.organization_id
                == organization_id,
                GovernedAIProviderCanaryHealthSnapshot.idempotency_key
                == idempotency_key,
            )
            .one()
        )
        return {
            "created": False,
            "item": _serialize_health(repeated),
            **list_canary_monitoring(
                db,
                organization_id=organization_id,
                connection_id=connection_id,
                now=occurred_at,
            ),
        }
    db.refresh(row)
    return {
        "created": True,
        "item": _serialize_health(row),
        **list_canary_monitoring(
            db,
            organization_id=organization_id,
            connection_id=connection_id,
            now=occurred_at,
        ),
    }


def set_provider_canary(
    db: Session,
    *,
    organization_id: str,
    connection_id: str,
    actor_user_id: str,
    action: str,
    client_request_id: str,
    acknowledgements: dict[str, bool],
    now: datetime | None = None,
) -> dict[str, Any]:
    if action not in {"enable", "disable"}:
        raise _error("Choose enable or disable.", "ai_provider_canary_action_invalid", 422)
    if action == "enable":
        require_commercial_feature(
            db,
            organization_id=organization_id,
            feature_code=FEATURE_PRIVATE_AI_PROVIDER,
        )
    request_id = client_request_id.strip()
    if len(request_id) < 8 or len(request_id) > 64:
        raise _error("The request identifier is invalid.", "ai_provider_canary_request_invalid", 422)

    occurred_at = _as_utc(now or datetime.now(UTC))
    organization = (
        db.query(Organization)
        .filter(Organization.id == organization_id)
        .populate_existing()
        .with_for_update()
        .one_or_none()
    )
    if organization is None:
        raise _error("Organization not found.", "organization_not_found", 404)
    connection = _connection(db, organization_id=organization_id, connection_id=connection_id)
    idempotency_key = _hash(
        {"organization_id": organization_id, "request_id": request_id}
    )
    existing = (
        db.query(GovernedAIProviderCanaryEvent)
        .filter(
            GovernedAIProviderCanaryEvent.organization_id == organization_id,
            GovernedAIProviderCanaryEvent.idempotency_key == idempotency_key,
        )
        .one_or_none()
    )
    if existing is not None:
        expected = "enabled" if action == "enable" else "disabled"
        if existing.connection_id != connection_id or existing.action != expected:
            raise _error(
                "This request identifier was already used differently.",
                "ai_provider_canary_request_conflict",
                409,
            )
        return _response(db, existing, created=False, now=occurred_at)

    readiness = _latest_readiness(
        db,
        organization_id=organization_id,
        connection_id=connection_id,
    )
    current = _latest_event(db, organization_id=organization_id)
    if current is not None and occurred_at <= _as_utc(current.created_at):
        occurred_at = _as_utc(current.created_at) + timedelta(microseconds=1)
    if action == "enable":
        if not all(acknowledgements.get(key) is True for key in _ACKS):
            raise _error(
                "Confirm every private-AI canary acknowledgement.",
                "ai_provider_canary_acknowledgement_required",
                422,
            )
        if current is not None and current.action == "enabled":
            raise _error(
                "Stop the current private-AI canary before starting another one.",
                "ai_provider_canary_already_enabled",
                409,
            )
        if not _readiness_current(
            db,
            readiness=readiness,
            connection=connection,
            now=occurred_at,
        ):
            raise _error(
                "Run the fallback readiness check again before starting the canary.",
                "ai_provider_canary_readiness_required",
                409,
            )
        row_action = "enabled"
        reason_code = "ai_provider_canary_owner_enabled"
        state = "canary"
        traffic = CANARY_TRAFFIC_PERCENTAGE
        prompts = True
        ack_payload = {key: True for key in _ACKS}
    else:
        if current is None or current.action != "enabled" or current.connection_id != connection_id:
            raise _error(
                "This private-AI canary is not active.",
                "ai_provider_canary_not_enabled",
                409,
            )
        readiness = _readiness_for_event(db, current)
        row_action = "disabled"
        reason_code = "ai_provider_canary_owner_disabled"
        state = "inactive"
        traffic = 0
        prompts = False
        ack_payload = {}

    if readiness is None:
        raise _error(
            "The fallback readiness evidence is unavailable.",
            "ai_provider_canary_readiness_required",
            409,
        )
    row = _new_event(
        organization_id=organization_id,
        connection_id=connection_id,
        readiness=readiness,
        action=row_action,
        state=state,
        traffic_percentage=traffic,
        customer_prompts_allowed=prompts,
        acknowledgements=ack_payload,
        reason_code=reason_code,
        idempotency_key=idempotency_key,
        actor_user_id=actor_user_id,
        now=occurred_at,
    )
    db.add(row)
    write_audit_log(
        db,
        tenant_id=organization_id,
        actor_user_id=actor_user_id,
        event_type=f"ai.provider_canary.{row_action}",
        payload={
            "connection_id": connection_id,
            "canary_event_id": row.id,
            "feature": CANARY_FEATURE,
            "traffic_percentage": traffic,
            "max_prompts_per_day": CANARY_DAILY_PROMPT_LIMIT,
            "automatic_rollback_enabled": True,
            "automatic_changes_allowed": False,
        },
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        repeated = (
            db.query(GovernedAIProviderCanaryEvent)
            .filter(
                GovernedAIProviderCanaryEvent.organization_id == organization_id,
                GovernedAIProviderCanaryEvent.idempotency_key == idempotency_key,
            )
            .one_or_none()
        )
        if repeated is None:
            raise
        return _response(db, repeated, created=False, now=occurred_at)
    db.refresh(row)
    return _response(db, row, created=True, now=occurred_at)


def select_canary_for_request(
    db: Session,
    *,
    organization_id: str,
    feature: str,
    request_key: str,
    now: datetime | None = None,
) -> CanarySelection | None:
    if feature != CANARY_FEATURE:
        return None
    occurred_at = _as_utc(now or datetime.now(UTC))
    event = _latest_event(db, organization_id=organization_id)
    if event is None or event.action != "enabled":
        return None
    connection = _connection_or_none(
        db,
        organization_id=organization_id,
        connection_id=event.connection_id,
    )
    if connection is None or not _event_evidence_current(
        db,
        event=event,
        connection=connection,
        now=occurred_at,
    ):
        return None
    used = _shared_daily_attempt_count(
        db,
        organization_id=organization_id,
        now=occurred_at,
    )
    if used >= CANARY_DAILY_PROMPT_LIMIT:
        return None
    bucket = int(sha256(request_key.encode("utf-8")).hexdigest()[:8], 16) % 100
    if bucket >= CANARY_TRAFFIC_PERCENTAGE:
        return None
    return CanarySelection(
        event_id=event.id,
        connection_id=connection.id,
        model_identifier=connection.model_identifier,
    )


def authorize_canary_dispatch(
    db: Session,
    *,
    organization_id: str,
    selection: CanarySelection,
    now: datetime | None = None,
) -> GovernedAIProviderCanaryEvent:
    occurred_at = _as_utc(now or datetime.now(UTC))
    organization = (
        db.query(Organization)
        .filter(Organization.id == organization_id)
        .populate_existing()
        .with_for_update()
        .one_or_none()
    )
    if organization is None:
        raise _error("Organization not found.", "organization_not_found", 404)
    event = _latest_event(db, organization_id=organization_id)
    connection = _connection_or_none(
        db,
        organization_id=organization_id,
        connection_id=selection.connection_id,
    )
    if (
        event is None
        or event.id != selection.event_id
        or event.action != "enabled"
        or connection is None
        or not _event_evidence_current(
            db,
            event=event,
            connection=connection,
            now=occurred_at,
        )
    ):
        raise _error(
            "The private-AI canary is no longer authorized.",
            "ai_provider_canary_not_current",
            409,
        )
    used = _shared_daily_attempt_count(
        db,
        organization_id=organization_id,
        now=occurred_at,
    )
    if used >= CANARY_DAILY_PROMPT_LIMIT:
        raise _error(
            "The private-AI canary has reached today's one-prompt limit.",
            "ai_provider_canary_daily_limit",
            409,
        )
    return event


def _shared_daily_attempt_count(
    db: Session,
    *,
    organization_id: str,
    now: datetime,
) -> int:
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    explanation_attempts = (
        db.query(GovernedAIProviderCanaryAttempt)
        .filter(
            GovernedAIProviderCanaryAttempt.organization_id == organization_id,
            GovernedAIProviderCanaryAttempt.created_at >= day_start,
        )
        .count()
    )
    question_attempts = 0
    if inspect(db.get_bind()).has_table(
        GovernedAIProviderCapabilityAttempt.__tablename__
    ):
        question_attempts = (
            db.query(GovernedAIProviderCapabilityAttempt)
            .filter(
                GovernedAIProviderCapabilityAttempt.organization_id == organization_id,
                GovernedAIProviderCapabilityAttempt.created_at >= day_start,
            )
            .count()
        )
    return explanation_attempts + question_attempts


def record_private_success(
    db: Session,
    *,
    event: GovernedAIProviderCanaryEvent,
    request_key: str,
    input_tokens: int,
    output_tokens: int,
    duration_ms: int = 0,
    now: datetime | None = None,
) -> GovernedAIProviderCanaryAttempt:
    return _record_attempt(
        db,
        event=event,
        request_key=request_key,
        outcome="private_succeeded",
        private_error_code=None,
        provider_may_have_processed=True,
        managed_fallback_used=False,
        automatic_rollback_triggered=False,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        duration_ms=duration_ms,
        now=now,
    )


def automatic_rollback(
    db: Session,
    *,
    event: GovernedAIProviderCanaryEvent,
    reason_code: str,
    now: datetime | None = None,
) -> GovernedAIProviderCanaryEvent:
    occurred_at = _as_utc(now or datetime.now(UTC))
    if occurred_at <= _as_utc(event.created_at):
        occurred_at = _as_utc(event.created_at) + timedelta(microseconds=1)
    latest = _latest_event(db, organization_id=event.organization_id)
    if latest is None or latest.id != event.id or latest.action != "enabled":
        return latest or event
    readiness = _readiness_for_event(db, event)
    if readiness is None:
        raise _error(
            "The canary readiness evidence is unavailable.",
            "ai_provider_canary_readiness_required",
            409,
        )
    rollback = _new_event(
        organization_id=event.organization_id,
        connection_id=event.connection_id,
        readiness=readiness,
        action="automatic_rollback",
        state="inactive",
        traffic_percentage=0,
        customer_prompts_allowed=False,
        acknowledgements={},
        reason_code=reason_code[:120],
        idempotency_key=_hash(
            {"event_id": event.id, "reason_code": reason_code, "kind": "rollback"}
        ),
        actor_user_id=None,
        now=occurred_at,
    )
    db.add(rollback)
    write_audit_log(
        db,
        tenant_id=event.organization_id,
        actor_user_id=None,
        event_type="ai.provider_canary.automatic_rollback",
        payload={
            "connection_id": event.connection_id,
            "previous_event_id": event.id,
            "canary_event_id": rollback.id,
            "reason_code": reason_code[:120],
            "traffic_percentage": 0,
            "managed_fallback_required": True,
        },
    )
    db.commit()
    db.refresh(rollback)
    return rollback


def record_managed_fallback(
    db: Session,
    *,
    event: GovernedAIProviderCanaryEvent,
    request_key: str,
    private_error_code: str,
    provider_may_have_processed: bool,
    managed_succeeded: bool,
    input_tokens: int,
    output_tokens: int,
    duration_ms: int = 0,
    now: datetime | None = None,
) -> GovernedAIProviderCanaryAttempt:
    return _record_attempt(
        db,
        event=event,
        request_key=request_key,
        outcome=(
            "managed_fallback_succeeded"
            if managed_succeeded
            else "managed_fallback_failed"
        ),
        private_error_code=private_error_code[:120],
        provider_may_have_processed=provider_may_have_processed,
        managed_fallback_used=True,
        automatic_rollback_triggered=True,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        duration_ms=duration_ms,
        now=now,
    )


def _record_attempt(
    db: Session,
    *,
    event: GovernedAIProviderCanaryEvent,
    request_key: str,
    outcome: str,
    private_error_code: str | None,
    provider_may_have_processed: bool,
    managed_fallback_used: bool,
    automatic_rollback_triggered: bool,
    input_tokens: int,
    output_tokens: int,
    duration_ms: int,
    now: datetime | None,
) -> GovernedAIProviderCanaryAttempt:
    occurred_at = _as_utc(now or datetime.now(UTC))
    request_hash = sha256(request_key.encode("utf-8")).hexdigest()
    artifact = {
        "event_id": event.id,
        "request_key_hash": request_hash,
        "outcome": outcome,
        "private_error_code": private_error_code,
        "provider_may_have_processed": provider_may_have_processed,
        "input_tokens": max(0, input_tokens),
        "output_tokens": max(0, output_tokens),
        "duration_ms": min(60_000, max(0, duration_ms)),
    }
    row = GovernedAIProviderCanaryAttempt(
        tenant_id=event.tenant_id,
        organization_id=event.organization_id,
        connection_id=event.connection_id,
        canary_event_id=event.id,
        feature=CANARY_FEATURE,
        outcome=outcome,
        request_key_hash=request_hash,
        private_error_code=private_error_code,
        customer_prompt_sent=True,
        provider_may_have_processed=provider_may_have_processed,
        managed_fallback_used=managed_fallback_used,
        automatic_rollback_triggered=automatic_rollback_triggered,
        automatic_changes_allowed=False,
        input_tokens=max(0, input_tokens),
        output_tokens=max(0, output_tokens),
        duration_ms=min(60_000, max(0, duration_ms)),
        cost_owner="customer",
        platform_provider_cost=0,
        artifact_hash=_hash(artifact),
        created_at=occurred_at,
    )
    db.add(row)
    write_audit_log(
        db,
        tenant_id=event.organization_id,
        actor_user_id=None,
        event_type=f"ai.provider_canary.attempt.{outcome}",
        payload={
            "connection_id": event.connection_id,
            "canary_event_id": event.id,
            "attempt_id": row.id,
            "outcome": outcome,
            "managed_fallback_used": managed_fallback_used,
            "automatic_rollback_triggered": automatic_rollback_triggered,
            "duration_ms": row.duration_ms,
            "automatic_changes_allowed": False,
        },
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = (
            db.query(GovernedAIProviderCanaryAttempt)
            .filter(
                GovernedAIProviderCanaryAttempt.organization_id
                == event.organization_id,
                GovernedAIProviderCanaryAttempt.request_key_hash == request_hash,
            )
            .one()
        )
        return existing
    db.refresh(row)
    return row


def _new_event(
    *,
    organization_id: str,
    connection_id: str,
    readiness: GovernedAIProviderRoutingReadiness,
    action: str,
    state: str,
    traffic_percentage: int,
    customer_prompts_allowed: bool,
    acknowledgements: dict[str, bool],
    reason_code: str,
    idempotency_key: str,
    actor_user_id: str | None,
    now: datetime,
) -> GovernedAIProviderCanaryEvent:
    artifact = {
        "connection_id": connection_id,
        "readiness_id": readiness.id,
        "readiness_artifact_hash": readiness.artifact_hash,
        "action": action,
        "state": state,
        "feature": CANARY_FEATURE,
        "traffic_percentage": traffic_percentage,
        "max_prompts_per_day": CANARY_DAILY_PROMPT_LIMIT,
        "customer_prompts_allowed": customer_prompts_allowed,
        "automatic_rollback_enabled": True,
        "automatic_changes_allowed": False,
        "acknowledgements": acknowledgements,
        "reason_code": reason_code,
    }
    return GovernedAIProviderCanaryEvent(
        tenant_id=organization_id,
        organization_id=organization_id,
        connection_id=connection_id,
        readiness_id=readiness.id,
        action=action,
        state=state,
        feature=CANARY_FEATURE,
        traffic_percentage=traffic_percentage,
        max_prompts_per_day=CANARY_DAILY_PROMPT_LIMIT,
        customer_prompts_allowed=customer_prompts_allowed,
        automatic_rollback_enabled=True,
        automatic_changes_allowed=False,
        automatic_activation_allowed=False,
        readiness_artifact_hash=readiness.artifact_hash,
        acknowledgements=acknowledgements,
        reason_code=reason_code,
        artifact_hash=_hash(artifact),
        idempotency_key=idempotency_key,
        created_by_user_id=actor_user_id,
        created_at=now,
    )


def _response(
    db: Session,
    row: GovernedAIProviderCanaryEvent,
    *,
    created: bool,
    now: datetime,
) -> dict[str, Any]:
    result = list_provider_canary(
        db,
        organization_id=row.organization_id,
        connection_id=row.connection_id,
        now=now,
    )
    return {"created": created, "item": _serialize_event(row), **result}


def _usage(db: Session, *, organization_id: str, now: datetime) -> dict[str, int]:
    start = now - timedelta(days=30)
    rows = (
        db.query(GovernedAIProviderCanaryAttempt)
        .filter(
            GovernedAIProviderCanaryAttempt.organization_id == organization_id,
            GovernedAIProviderCanaryAttempt.created_at >= start,
        )
        .all()
    )
    return {
        "window_days": 30,
        "private_attempts": len(rows),
        "private_successes": sum(row.outcome == "private_succeeded" for row in rows),
        "managed_fallbacks": sum(row.managed_fallback_used for row in rows),
        "automatic_rollbacks": sum(row.automatic_rollback_triggered for row in rows),
        "input_tokens": sum(max(0, row.input_tokens) for row in rows),
        "output_tokens": sum(max(0, row.output_tokens) for row in rows),
    }


def _monitoring_evidence(
    db: Session,
    *,
    organization_id: str,
    connection: GovernedAIProviderConnection,
    now: datetime,
) -> dict[str, Any]:
    start = now - timedelta(days=CANARY_MONITORING_WINDOW_DAYS)
    attempts = (
        db.query(GovernedAIProviderCanaryAttempt)
        .filter(
            GovernedAIProviderCanaryAttempt.organization_id == organization_id,
            GovernedAIProviderCanaryAttempt.connection_id == connection.id,
            GovernedAIProviderCanaryAttempt.created_at >= start,
        )
        .order_by(GovernedAIProviderCanaryAttempt.created_at.asc())
        .all()
    )
    successes = [row for row in attempts if row.outcome == "private_succeeded"]
    distinct_days = {
        _as_utc(row.created_at).date().isoformat() for row in successes
    }
    managed_fallbacks = sum(row.managed_fallback_used for row in attempts)
    automatic_rollbacks = sum(row.automatic_rollback_triggered for row in attempts)
    max_latency = max((max(0, row.duration_ms) for row in successes), default=0)
    enabled_event = _latest_enabled_event(
        db,
        organization_id=organization_id,
        connection_id=connection.id,
    )
    current_event = _latest_event(db, organization_id=organization_id)
    hard_blockers: list[dict[str, str]] = []
    collecting_blockers: list[dict[str, str]] = []
    if enabled_event is None:
        hard_blockers.append(
            {
                "code": "canary_not_started",
                "summary": "The fixed private-AI check has not been started.",
            }
        )
    else:
        if (
            current_event is None
            or current_event.id != enabled_event.id
            or current_event.action != "enabled"
        ):
            hard_blockers.append(
                {
                    "code": "canary_not_active",
                    "summary": "The fixed private-AI check is not currently active.",
                }
            )
        elif not _event_evidence_current(
            db,
            event=enabled_event,
            connection=connection,
            now=now,
        ):
            hard_blockers.append(
                {
                    "code": "canary_safety_evidence_not_current",
                    "summary": "The saved safety and fallback checks need to be refreshed.",
                }
            )
    if managed_fallbacks:
        hard_blockers.append(
            {
                "code": "managed_fallback_observed",
                "summary": "At least one private attempt required managed fallback.",
            }
        )
    if automatic_rollbacks:
        hard_blockers.append(
            {
                "code": "automatic_rollback_observed",
                "summary": "At least one private attempt triggered the automatic stop.",
            }
        )
    if max_latency > CANARY_MAX_LATENCY_MS:
        hard_blockers.append(
            {
                "code": "private_latency_above_threshold",
                "summary": "A successful private response exceeded the eight-second health limit.",
            }
        )
    if len(distinct_days) < CANARY_REQUIRED_SUCCESS_DAYS:
        collecting_blockers.append(
            {
                "code": "more_successful_days_required",
                "summary": (
                    f"Collect successful checks on {CANARY_REQUIRED_SUCCESS_DAYS - len(distinct_days)} "
                    "more separate day(s)."
                ),
            }
        )
    status = (
        "not_started"
        if enabled_event is None
        else "blocked"
        if hard_blockers
        else "collecting"
        if collecting_blockers
        else "eligible_for_later_review"
    )
    return {
        "status": status,
        "feature": CANARY_FEATURE,
        "window_days": CANARY_MONITORING_WINDOW_DAYS,
        "required_success_days": CANARY_REQUIRED_SUCCESS_DAYS,
        "max_latency_threshold_ms": CANARY_MAX_LATENCY_MS,
        "private_successes": len(successes),
        "distinct_success_days": len(distinct_days),
        "successful_days_remaining": max(
            0, CANARY_REQUIRED_SUCCESS_DAYS - len(distinct_days)
        ),
        "managed_fallbacks": managed_fallbacks,
        "automatic_rollbacks": automatic_rollbacks,
        "max_latency_ms": min(60_000, max_latency),
        "blockers": hard_blockers + collecting_blockers,
        "evidence_only": True,
    }


def _monitoring_summary(status: str) -> str:
    if status == "eligible_for_later_review":
        return (
            "The saved canary history meets the minimum evidence threshold for a "
            "separate later capability review. Traffic and capabilities did not change."
        )
    if status == "collecting":
        return "Keep the fixed check in place while more successful days are collected."
    if status == "blocked":
        return "The saved canary history has a blocker and cannot support a later review."
    return "Start the fixed private-AI check before reviewing multi-run health."


def _serialize_health(
    row: GovernedAIProviderCanaryHealthSnapshot,
) -> dict[str, Any]:
    return {
        "id": row.id,
        "connection_id": row.connection_id,
        "canary_event_id": row.canary_event_id,
        "feature": row.feature,
        "status": row.status,
        "window_days": row.window_days,
        "required_success_days": row.required_success_days,
        "max_latency_threshold_ms": row.max_latency_threshold_ms,
        "private_successes": row.private_successes,
        "distinct_success_days": row.distinct_success_days,
        "managed_fallbacks": row.managed_fallbacks,
        "automatic_rollbacks": row.automatic_rollbacks,
        "max_latency_ms": row.max_latency_ms,
        "blockers": row.blockers,
        "traffic_change_allowed": False,
        "capability_change_allowed": False,
        "automatic_activation_allowed": False,
        "automatic_changes_allowed": False,
        "created_at": row.created_at.isoformat(),
        "immutable": True,
    }


def _latest_event(db: Session, *, organization_id: str) -> GovernedAIProviderCanaryEvent | None:
    return (
        db.query(GovernedAIProviderCanaryEvent)
        .filter(GovernedAIProviderCanaryEvent.organization_id == organization_id)
        .order_by(
            GovernedAIProviderCanaryEvent.created_at.desc(),
            GovernedAIProviderCanaryEvent.id.desc(),
        )
        .first()
    )


def _latest_enabled_event(
    db: Session,
    *,
    organization_id: str,
    connection_id: str,
) -> GovernedAIProviderCanaryEvent | None:
    return (
        db.query(GovernedAIProviderCanaryEvent)
        .filter(
            GovernedAIProviderCanaryEvent.organization_id == organization_id,
            GovernedAIProviderCanaryEvent.connection_id == connection_id,
            GovernedAIProviderCanaryEvent.action == "enabled",
        )
        .order_by(
            GovernedAIProviderCanaryEvent.created_at.desc(),
            GovernedAIProviderCanaryEvent.id.desc(),
        )
        .first()
    )


def _latest_readiness(
    db: Session,
    *,
    organization_id: str,
    connection_id: str,
) -> GovernedAIProviderRoutingReadiness | None:
    return (
        db.query(GovernedAIProviderRoutingReadiness)
        .filter(
            GovernedAIProviderRoutingReadiness.organization_id == organization_id,
            GovernedAIProviderRoutingReadiness.connection_id == connection_id,
        )
        .order_by(
            GovernedAIProviderRoutingReadiness.created_at.desc(),
            GovernedAIProviderRoutingReadiness.id.desc(),
        )
        .first()
    )


def _readiness_for_event(
    db: Session,
    event: GovernedAIProviderCanaryEvent,
) -> GovernedAIProviderRoutingReadiness | None:
    return (
        db.query(GovernedAIProviderRoutingReadiness)
        .filter(
            GovernedAIProviderRoutingReadiness.id == event.readiness_id,
            GovernedAIProviderRoutingReadiness.organization_id == event.organization_id,
            GovernedAIProviderRoutingReadiness.connection_id == event.connection_id,
        )
        .one_or_none()
    )


def _readiness_current(
    db: Session,
    *,
    readiness: GovernedAIProviderRoutingReadiness | None,
    connection: GovernedAIProviderConnection,
    now: datetime,
) -> bool:
    standby = current_provider_standby_event(
        db,
        organization_id=connection.organization_id,
        connection=connection,
    )
    return bool(
        readiness
        and _private_ai_feature_allowed(db, organization_id=connection.organization_id)
        and readiness.status == "passed"
        and readiness.rollback_ready
        and readiness.standby_evidence_current
        and readiness.standby_event_id == (standby.id if standby else None)
        and _as_utc(readiness.created_at) >= now - _READINESS_MAX_AGE
        and readiness.managed_evidence_at is not None
        and _as_utc(readiness.managed_evidence_at) >= now - _READINESS_MAX_AGE
        and connection.status == "candidate"
        and connection.validation_status == "passed"
        and connection.network_validation_status == "passed"
        and bool(connection.encrypted_config_blob)
        and len(connection.model_identifier) <= 120
    )


def _private_ai_feature_allowed(db: Session, *, organization_id: str) -> bool:
    try:
        require_commercial_feature(
            db,
            organization_id=organization_id,
            feature_code=FEATURE_PRIVATE_AI_PROVIDER,
        )
    except CostEconomicsError:
        return False
    return True


def _event_evidence_current(
    db: Session,
    *,
    event: GovernedAIProviderCanaryEvent,
    connection: GovernedAIProviderConnection,
    now: datetime,
) -> bool:
    readiness = _latest_readiness(
        db,
        organization_id=event.organization_id,
        connection_id=event.connection_id,
    )
    return bool(
        readiness
        and readiness.id == event.readiness_id
        and readiness.artifact_hash == event.readiness_artifact_hash
        and _readiness_current(db, readiness=readiness, connection=connection, now=now)
    )


def _connection(
    db: Session,
    *,
    organization_id: str,
    connection_id: str,
) -> GovernedAIProviderConnection:
    row = _connection_or_none(
        db,
        organization_id=organization_id,
        connection_id=connection_id,
    )
    if row is None:
        raise _error(
            "Private AI provider not found.",
            "ai_provider_connection_not_found",
            404,
        )
    return row


def _connection_or_none(
    db: Session,
    *,
    organization_id: str,
    connection_id: str,
) -> GovernedAIProviderConnection | None:
    return (
        db.query(GovernedAIProviderConnection)
        .filter(
            GovernedAIProviderConnection.id == connection_id,
            GovernedAIProviderConnection.organization_id == organization_id,
        )
        .populate_existing()
        .one_or_none()
    )


def _serialize_event(row: GovernedAIProviderCanaryEvent | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": row.id,
        "connection_id": row.connection_id,
        "action": row.action,
        "state": row.state,
        "feature": row.feature,
        "traffic_percentage": row.traffic_percentage,
        "max_prompts_per_day": row.max_prompts_per_day,
        "customer_prompts_allowed": row.customer_prompts_allowed,
        "automatic_rollback_enabled": row.automatic_rollback_enabled,
        "automatic_changes_allowed": False,
        "automatic_activation_allowed": False,
        "reason_code": row.reason_code,
        "created_at": row.created_at.isoformat(),
        "immutable": True,
    }


def _hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(encoded).hexdigest()


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _error(message: str, reason_code: str, status_code: int) -> GovernedAIProviderConnectionError:
    return GovernedAIProviderConnectionError(
        message,
        reason_code=reason_code,
        status_code=status_code,
    )

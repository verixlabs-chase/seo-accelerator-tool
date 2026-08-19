from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any

from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.governed_ai_provider_canary import (
    GovernedAIProviderCanaryHealthSnapshot,
)
from app.models.governed_ai_provider_capability import (
    GovernedAIProviderCapabilityAttempt,
    GovernedAIProviderCapabilityBenchmark,
    GovernedAIProviderCapabilityEvent,
)
from app.services.audit_service import write_audit_log
from app.services.commercial_plan_service import (
    FEATURE_PRIVATE_AI_PROVIDER,
    require_commercial_feature,
)
from app.services.governed_ai_provider_capability_service import (
    CapabilitySelection,
    SHARED_DAILY_PROMPT_LIMIT,
    TRAFFIC_PERCENTAGE,
    _as_utc,
    _capability_tables_available,
    _connection,
    _connection_or_none,
    _error,
    _hash,
    _locked_organization,
    _request_id,
    _shared_daily_attempts,
)
from app.services.governed_ai_provider_review_response_capability_service import (
    CAPABILITY,
    _benchmark_current,
    _latest_benchmark,
    list_review_response_qualification,
)


_ACKS = (
    "reviewed_review_reply_check",
    "understands_real_saved_review_context",
    "understands_shared_daily_limit",
    "understands_managed_fallback_and_rollback",
    "understands_draft_only_no_posting",
)


def list_review_response_capability(
    db: Session,
    *,
    organization_id: str,
    connection_id: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    occurred_at = _as_utc(now or datetime.now(UTC))
    base = list_review_response_qualification(
        db,
        organization_id=organization_id,
        connection_id=connection_id,
        now=occurred_at,
    )
    if not _runtime_schema_available(db):
        return base
    connection = _connection(
        db, organization_id=organization_id, connection_id=connection_id
    )
    benchmark = _latest_benchmark(
        db, organization_id=organization_id, connection_id=connection_id
    )
    benchmark_current = _benchmark_current(
        db, benchmark=benchmark, connection=connection, now=occurred_at
    )
    current = _latest_event(db, organization_id=organization_id)
    recorded_here = bool(
        current and current.action == "enabled" and current.connection_id == connection_id
    )
    active_here = bool(
        recorded_here
        and _event_current(db, event=current, connection_id=connection_id, now=occurred_at)
    )
    active_elsewhere = bool(
        current and current.action == "enabled" and current.connection_id != connection_id
    )
    state = (
        "capability_canary"
        if active_here
        else "needs_attention"
        if recorded_here
        else "capability_canary_elsewhere"
        if active_elsewhere
        else "eligible_for_owner_approval"
        if benchmark_current
        else base["state"]
    )
    return {
        **base,
        "state": state,
        "current": _serialize_event(current) if current else None,
        "routing_enabled": active_here,
        "traffic_percentage": TRAFFIC_PERCENTAGE if active_here else 0,
        "max_prompts_per_day": SHARED_DAILY_PROMPT_LIMIT,
        "daily_limit_shared_with_other_private_ai": True,
        "customer_prompts_allowed": active_here,
        "owner_activation_available": benchmark_current,
        "automatic_rollback_enabled": True,
        "usage": _usage(db, organization_id=organization_id, now=occurred_at),
        "qualification_only": False,
        "truth": {"state": state, "summary": _summary(state)},
    }


def set_review_response_capability(
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
    _require_runtime_schema(db)
    if action not in {"enable", "disable"}:
        raise _error(
            "Choose enable or disable.", "ai_provider_capability_action_invalid", 422
        )
    if action == "enable":
        require_commercial_feature(
            db,
            organization_id=organization_id,
            feature_code=FEATURE_PRIVATE_AI_PROVIDER,
        )
    request_id = _request_id(client_request_id)
    occurred_at = _as_utc(now or datetime.now(UTC))
    organization = _locked_organization(db, organization_id=organization_id)
    connection = _connection(
        db, organization_id=organization_id, connection_id=connection_id
    )
    idempotency_key = _hash(
        {
            "organization_id": organization_id,
            "request_id": request_id,
            "kind": "review_response_capability_event",
        }
    )
    existing = _event_by_idempotency(
        db, organization_id=organization_id, idempotency_key=idempotency_key
    )
    if existing is not None:
        expected = "enabled" if action == "enable" else "disabled"
        if existing.connection_id != connection_id or existing.action != expected:
            raise _error(
                "This request identifier was already used differently.",
                "ai_provider_capability_request_conflict",
                409,
            )
        return _event_response(db, existing, created=False, now=occurred_at)
    current = _latest_event(db, organization_id=organization_id)
    if current is not None and occurred_at <= _as_utc(current.created_at):
        occurred_at = _as_utc(current.created_at) + timedelta(microseconds=1)
    if action == "enable":
        if not all(acknowledgements.get(key) is True for key in _ACKS):
            raise _error(
                "Confirm every review-reply capability acknowledgement.",
                "ai_provider_review_response_acknowledgement_required",
                422,
            )
        if current is not None and current.action == "enabled":
            raise _error(
                "Stop the current review-reply check before starting another one.",
                "ai_provider_review_response_already_enabled",
                409,
            )
        benchmark = _latest_benchmark(
            db, organization_id=organization_id, connection_id=connection_id
        )
        if not _benchmark_current(
            db, benchmark=benchmark, connection=connection, now=occurred_at
        ):
            raise _error(
                "Run the review-reply compatibility check again before enabling it.",
                "ai_provider_review_response_benchmark_required",
                409,
            )
        assert benchmark is not None
        health = db.get(
            GovernedAIProviderCanaryHealthSnapshot, benchmark.health_snapshot_id
        )
        if health is None:
            raise _error(
                "The private-AI health evidence is unavailable.",
                "ai_provider_capability_health_required",
                409,
            )
        row_action, state, traffic, prompts = "enabled", "capability_canary", 5, True
        reason = "ai_provider_review_response_owner_enabled"
        ack_payload = {key: True for key in _ACKS}
    else:
        if (
            current is None
            or current.action != "enabled"
            or current.connection_id != connection_id
        ):
            raise _error(
                "This review-reply capability is not active.",
                "ai_provider_review_response_not_enabled",
                409,
            )
        benchmark = db.get(GovernedAIProviderCapabilityBenchmark, current.benchmark_id)
        health = db.get(
            GovernedAIProviderCanaryHealthSnapshot, current.health_snapshot_id
        )
        if benchmark is None or health is None:
            raise _error(
                "The capability evidence is unavailable.",
                "ai_provider_capability_evidence_required",
                409,
            )
        row_action, state, traffic, prompts = "disabled", "inactive", 0, False
        reason = "ai_provider_review_response_owner_disabled"
        ack_payload = {}
    row = _new_event(
        organization_id=organization_id,
        connection_id=connection_id,
        health=health,
        benchmark=benchmark,
        action=row_action,
        state=state,
        traffic_percentage=traffic,
        customer_prompts_allowed=prompts,
        acknowledgements=ack_payload,
        reason_code=reason,
        idempotency_key=idempotency_key,
        actor_user_id=actor_user_id,
        now=occurred_at,
    )
    db.add(row)
    write_audit_log(
        db,
        tenant_id=organization.id,
        actor_user_id=actor_user_id,
        event_type=f"ai.provider_capability.review_response_{row_action}",
        payload={
            "connection_id": connection_id,
            "capability_event_id": row.id,
            "capability": CAPABILITY,
            "traffic_percentage": traffic,
            "shared_daily_prompt_limit": SHARED_DAILY_PROMPT_LIMIT,
            "draft_only": True,
            "customer_review_sent": False,
            "review_status_changed": False,
            "may_post_response": False,
            "publishing_allowed": False,
        },
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        repeated = _event_by_idempotency(
            db, organization_id=organization_id, idempotency_key=idempotency_key
        )
        assert repeated is not None
        return _event_response(db, repeated, created=False, now=occurred_at)
    db.refresh(row)
    return _event_response(db, row, created=True, now=occurred_at)


def select_review_response_capability(
    db: Session,
    *,
    organization_id: str,
    request_key: str,
    now: datetime | None = None,
) -> CapabilitySelection | None:
    if not _runtime_schema_available(db):
        return None
    occurred_at = _as_utc(now or datetime.now(UTC))
    event = _latest_event(db, organization_id=organization_id)
    if event is None or event.action != "enabled":
        return None
    connection = _connection_or_none(
        db, organization_id=organization_id, connection_id=event.connection_id
    )
    if connection is None or not _event_current(
        db, event=event, connection_id=connection.id, now=occurred_at
    ):
        return None
    if _shared_daily_attempts(db, organization_id=organization_id, now=occurred_at) >= 1:
        return None
    bucket = int(sha256(request_key.encode("utf-8")).hexdigest()[:8], 16) % 100
    if bucket >= TRAFFIC_PERCENTAGE:
        return None
    return CapabilitySelection(
        event_id=event.id,
        connection_id=connection.id,
        model_identifier=connection.model_identifier,
    )


def authorize_review_response_dispatch(
    db: Session,
    *,
    organization_id: str,
    selection: CapabilitySelection,
    now: datetime | None = None,
) -> GovernedAIProviderCapabilityEvent:
    _require_runtime_schema(db)
    occurred_at = _as_utc(now or datetime.now(UTC))
    _locked_organization(db, organization_id=organization_id)
    event = _latest_event(db, organization_id=organization_id)
    if (
        event is None
        or event.id != selection.event_id
        or event.action != "enabled"
        or not _event_current(
            db,
            event=event,
            connection_id=selection.connection_id,
            now=occurred_at,
        )
    ):
        raise _error(
            "The review-reply private-AI capability is no longer authorized.",
            "ai_provider_review_response_not_current",
            409,
        )
    if _shared_daily_attempts(db, organization_id=organization_id, now=occurred_at) >= 1:
        raise _error(
            "The shared private-AI check has reached today's one-prompt limit.",
            "ai_provider_shared_daily_limit",
            409,
        )
    return event


def automatic_review_response_rollback(
    db: Session,
    *,
    event: GovernedAIProviderCapabilityEvent,
    reason_code: str,
    now: datetime | None = None,
) -> GovernedAIProviderCapabilityEvent:
    occurred_at = _as_utc(now or datetime.now(UTC))
    if occurred_at <= _as_utc(event.created_at):
        occurred_at = _as_utc(event.created_at) + timedelta(microseconds=1)
    latest = _latest_event(db, organization_id=event.organization_id)
    if latest is None or latest.id != event.id or latest.action != "enabled":
        return latest or event
    health = db.get(GovernedAIProviderCanaryHealthSnapshot, event.health_snapshot_id)
    benchmark = db.get(GovernedAIProviderCapabilityBenchmark, event.benchmark_id)
    if health is None or benchmark is None:
        raise _error(
            "The capability evidence is unavailable.",
            "ai_provider_capability_evidence_required",
            409,
        )
    rollback = _new_event(
        organization_id=event.organization_id,
        connection_id=event.connection_id,
        health=health,
        benchmark=benchmark,
        action="automatic_rollback",
        state="inactive",
        traffic_percentage=0,
        customer_prompts_allowed=False,
        acknowledgements={},
        reason_code=reason_code[:120],
        idempotency_key=_hash(
            {
                "event_id": event.id,
                "reason_code": reason_code,
                "kind": "review_response_capability_rollback",
            }
        ),
        actor_user_id=None,
        now=occurred_at,
    )
    db.add(rollback)
    write_audit_log(
        db,
        tenant_id=event.organization_id,
        actor_user_id=None,
        event_type="ai.provider_capability.review_response_automatic_rollback",
        payload={
            "connection_id": event.connection_id,
            "previous_event_id": event.id,
            "capability_event_id": rollback.id,
            "reason_code": reason_code[:120],
            "traffic_percentage": 0,
            "managed_fallback_required": True,
            "draft_only": True,
            "may_post_response": False,
            "publishing_allowed": False,
        },
    )
    db.commit()
    db.refresh(rollback)
    return rollback


def record_review_response_success(
    db: Session,
    *,
    event: GovernedAIProviderCapabilityEvent,
    request_key: str,
    input_tokens: int,
    output_tokens: int,
    duration_ms: int,
    now: datetime | None = None,
) -> GovernedAIProviderCapabilityAttempt:
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


def record_review_response_fallback(
    db: Session,
    *,
    event: GovernedAIProviderCapabilityEvent,
    request_key: str,
    private_error_code: str,
    provider_may_have_processed: bool,
    managed_succeeded: bool,
    input_tokens: int,
    output_tokens: int,
    duration_ms: int,
    now: datetime | None = None,
) -> GovernedAIProviderCapabilityAttempt:
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
    event: GovernedAIProviderCapabilityEvent,
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
) -> GovernedAIProviderCapabilityAttempt:
    occurred_at = _as_utc(now or datetime.now(UTC))
    request_hash = sha256(request_key.encode("utf-8")).hexdigest()
    row = GovernedAIProviderCapabilityAttempt(
        tenant_id=event.tenant_id,
        organization_id=event.organization_id,
        connection_id=event.connection_id,
        capability_event_id=event.id,
        capability=CAPABILITY,
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
        artifact_hash=_hash(
            {
                "event_id": event.id,
                "capability": CAPABILITY,
                "request_key_hash": request_hash,
                "outcome": outcome,
                "private_error_code": private_error_code,
                "provider_may_have_processed": provider_may_have_processed,
                "input_tokens": max(0, input_tokens),
                "output_tokens": max(0, output_tokens),
                "duration_ms": min(60_000, max(0, duration_ms)),
            }
        ),
        created_at=occurred_at,
    )
    db.add(row)
    write_audit_log(
        db,
        tenant_id=event.organization_id,
        actor_user_id=None,
        event_type=f"ai.provider_capability.review_response_attempt.{outcome}",
        payload={
            "connection_id": event.connection_id,
            "capability_event_id": event.id,
            "attempt_id": row.id,
            "outcome": outcome,
            "managed_fallback_used": managed_fallback_used,
            "automatic_rollback_triggered": automatic_rollback_triggered,
            "draft_only": True,
            "customer_review_sent": False,
            "review_status_changed": False,
            "may_post_response": False,
        },
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        existing = (
            db.query(GovernedAIProviderCapabilityAttempt)
            .filter(
                GovernedAIProviderCapabilityAttempt.organization_id
                == event.organization_id,
                GovernedAIProviderCapabilityAttempt.request_key_hash == request_hash,
            )
            .one_or_none()
        )
        if existing is None:
            raise exc
        return existing
    db.refresh(row)
    return row


def _event_current(
    db: Session,
    *,
    event: GovernedAIProviderCapabilityEvent,
    connection_id: str,
    now: datetime,
) -> bool:
    if event.capability != CAPABILITY or event.connection_id != connection_id:
        return False
    connection = _connection_or_none(
        db, organization_id=event.organization_id, connection_id=connection_id
    )
    benchmark = db.get(GovernedAIProviderCapabilityBenchmark, event.benchmark_id)
    health = db.get(GovernedAIProviderCanaryHealthSnapshot, event.health_snapshot_id)
    if connection is None or benchmark is None or health is None:
        return False
    return bool(
        benchmark.capability == CAPABILITY
        and benchmark.connection_id == connection_id
        and benchmark.health_snapshot_id == health.id
        and _benchmark_current(db, benchmark=benchmark, connection=connection, now=now)
    )


def _new_event(
    *,
    organization_id: str,
    connection_id: str,
    health: GovernedAIProviderCanaryHealthSnapshot,
    benchmark: GovernedAIProviderCapabilityBenchmark,
    action: str,
    state: str,
    traffic_percentage: int,
    customer_prompts_allowed: bool,
    acknowledgements: dict[str, bool],
    reason_code: str,
    idempotency_key: str,
    actor_user_id: str | None,
    now: datetime,
) -> GovernedAIProviderCapabilityEvent:
    artifact = {
        "organization_id": organization_id,
        "connection_id": connection_id,
        "health_snapshot_id": health.id,
        "benchmark_id": benchmark.id,
        "action": action,
        "state": state,
        "capability": CAPABILITY,
        "traffic_percentage": traffic_percentage,
        "max_prompts_per_day": SHARED_DAILY_PROMPT_LIMIT,
        "customer_prompts_allowed": customer_prompts_allowed,
        "automatic_rollback_enabled": True,
        "automatic_activation_allowed": False,
        "automatic_changes_allowed": False,
        "acknowledgements": acknowledgements,
        "reason_code": reason_code,
    }
    return GovernedAIProviderCapabilityEvent(
        tenant_id=organization_id,
        organization_id=organization_id,
        connection_id=connection_id,
        health_snapshot_id=health.id,
        benchmark_id=benchmark.id,
        action=action,
        state=state,
        capability=CAPABILITY,
        traffic_percentage=traffic_percentage,
        max_prompts_per_day=SHARED_DAILY_PROMPT_LIMIT,
        customer_prompts_allowed=customer_prompts_allowed,
        automatic_rollback_enabled=True,
        automatic_activation_allowed=False,
        automatic_changes_allowed=False,
        acknowledgements=acknowledgements,
        reason_code=reason_code,
        artifact_hash=_hash(artifact),
        idempotency_key=idempotency_key,
        created_by_user_id=actor_user_id,
        created_at=now,
    )


def _latest_event(
    db: Session, *, organization_id: str
) -> GovernedAIProviderCapabilityEvent | None:
    return (
        db.query(GovernedAIProviderCapabilityEvent)
        .filter(
            GovernedAIProviderCapabilityEvent.organization_id == organization_id,
            GovernedAIProviderCapabilityEvent.capability == CAPABILITY,
        )
        .order_by(
            GovernedAIProviderCapabilityEvent.created_at.desc(),
            GovernedAIProviderCapabilityEvent.id.desc(),
        )
        .first()
    )


def _event_by_idempotency(
    db: Session, *, organization_id: str, idempotency_key: str
) -> GovernedAIProviderCapabilityEvent | None:
    return (
        db.query(GovernedAIProviderCapabilityEvent)
        .filter(
            GovernedAIProviderCapabilityEvent.organization_id == organization_id,
            GovernedAIProviderCapabilityEvent.idempotency_key == idempotency_key,
        )
        .one_or_none()
    )


def _usage(db: Session, *, organization_id: str, now: datetime) -> dict[str, int]:
    rows = (
        db.query(GovernedAIProviderCapabilityAttempt)
        .filter(
            GovernedAIProviderCapabilityAttempt.organization_id == organization_id,
            GovernedAIProviderCapabilityAttempt.capability == CAPABILITY,
            GovernedAIProviderCapabilityAttempt.created_at >= now - timedelta(days=30),
        )
        .all()
    )
    return {
        "private_attempts": len(rows),
        "private_successes": sum(row.outcome == "private_succeeded" for row in rows),
        "managed_fallbacks": sum(row.managed_fallback_used for row in rows),
        "automatic_rollbacks": sum(
            row.automatic_rollback_triggered for row in rows
        ),
    }


def _serialize_event(row: GovernedAIProviderCapabilityEvent) -> dict[str, Any]:
    return {
        "id": row.id,
        "connection_id": row.connection_id,
        "action": row.action,
        "state": row.state,
        "capability": row.capability,
        "traffic_percentage": row.traffic_percentage,
        "max_prompts_per_day": row.max_prompts_per_day,
        "customer_prompts_allowed": row.customer_prompts_allowed,
        "automatic_rollback_enabled": row.automatic_rollback_enabled,
        "automatic_activation_allowed": False,
        "automatic_changes_allowed": False,
        "draft_only": True,
        "customer_review_sent": False,
        "review_status_changed": False,
        "may_post_response": False,
        "publishing_allowed": False,
        "reason_code": row.reason_code,
        "created_at": _as_utc(row.created_at).isoformat(),
        "immutable": True,
    }


def _event_response(
    db: Session,
    row: GovernedAIProviderCapabilityEvent,
    *,
    created: bool,
    now: datetime,
) -> dict[str, Any]:
    return {
        "created": created,
        "item": _serialize_event(row),
        **list_review_response_capability(
            db,
            organization_id=row.organization_id,
            connection_id=row.connection_id,
            now=now,
        ),
    }


def _runtime_schema_available(db: Session) -> bool:
    if not _capability_tables_available(db):
        return False
    try:
        event_constraints = inspect(db.get_bind()).get_check_constraints(
            GovernedAIProviderCapabilityEvent.__tablename__
        )
        attempt_constraints = inspect(db.get_bind()).get_check_constraints(
            GovernedAIProviderCapabilityAttempt.__tablename__
        )
    except Exception:
        return False
    return bool(
        any(CAPABILITY in str(item.get("sqltext") or "") for item in event_constraints)
        and any(
            CAPABILITY in str(item.get("sqltext") or "")
            for item in attempt_constraints
        )
    )


def _require_runtime_schema(db: Session) -> None:
    if not _runtime_schema_available(db):
        raise _error(
            "Review-reply private AI is not available yet.",
            "ai_provider_review_response_canary_unavailable",
            409,
        )


def _summary(state: str) -> str:
    if state == "capability_canary":
        return "The limited review-reply wording check is on. Every reply remains a draft."
    if state == "eligible_for_owner_approval":
        return "The made-up review reply check passed and is ready for owner review."
    if state == "capability_canary_elsewhere":
        return "Another private provider owns this limited review-reply check."
    if state == "needs_attention":
        return "The saved review-reply check needs attention; customer reviews remain off."
    if state == "qualification_failed":
        return "The made-up review reply check did not pass; no customer review was sent."
    return "Run the made-up review reply check before considering limited use."

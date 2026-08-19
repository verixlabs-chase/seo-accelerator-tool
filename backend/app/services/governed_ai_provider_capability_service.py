from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
from time import perf_counter
from typing import Any

from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.intelligence.contracts.governed_ai import GovernedEvidenceAnswer
from app.models.governed_ai_provider_canary import (
    GovernedAIProviderCanaryAttempt,
    GovernedAIProviderCanaryHealthSnapshot,
)
from app.models.governed_ai_provider_capability import (
    GovernedAIProviderCapabilityAttempt,
    GovernedAIProviderCapabilityBenchmark,
    GovernedAIProviderCapabilityEvent,
)
from app.models.governed_ai_provider_connection import GovernedAIProviderConnection
from app.models.organization import Organization
from app.services.audit_service import write_audit_log
from app.services.commercial_plan_service import (
    FEATURE_PRIVATE_AI_PROVIDER,
    require_commercial_feature,
)
from app.services.cost_economics_service import CostEconomicsError
from app.services.governed_ai_provider import GovernedAIProviderError
from app.services.governed_ai_provider_canary_service import (
    list_canary_monitoring,
    list_provider_canary,
)
from app.services.governed_ai_provider_connection_service import (
    GovernedAIProviderConnectionError,
    open_pinned_runtime_provider,
)


CAPABILITY = "intelligence_question"
CAPABILITY_SCHEMA_VERSION = "governed-evidence-answer-v1"
TRAFFIC_PERCENTAGE = 5
SHARED_DAILY_PROMPT_LIMIT = 1
_ACKS = (
    "reviewed_question_capability_check",
    "understands_real_customer_questions",
    "understands_shared_daily_limit",
    "understands_managed_fallback_and_rollback",
    "understands_no_automatic_changes",
)
_SYNTHETIC_QUESTION = "Which saved action should I review first?"
_SYNTHETIC_EVIDENCE_ID = "evidence:synthetic:action"
_SYNTHETIC_ACTION_ID = "action:synthetic:review"


@dataclass(frozen=True)
class CapabilitySelection:
    event_id: str
    connection_id: str
    model_identifier: str


def list_question_capability(
    db: Session,
    *,
    organization_id: str,
    connection_id: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    occurred_at = _as_utc(now or datetime.now(UTC))
    connection = _connection(db, organization_id=organization_id, connection_id=connection_id)
    if not _capability_tables_available(db):
        return _unavailable_capability()
    benchmark = _latest_benchmark(
        db,
        organization_id=organization_id,
        connection_id=connection_id,
    )
    current = _latest_event(db, organization_id=organization_id)
    recorded_here = bool(
        current and current.action == "enabled" and current.connection_id == connection_id
    )
    active_here = bool(
        recorded_here
        and _event_current(
            db,
            event=current,
            connection=connection,
            now=occurred_at,
        )
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
        if _benchmark_current(
            db,
            benchmark=benchmark,
            connection=connection,
            now=occurred_at,
        )
        else "qualification_failed"
        if benchmark is not None and benchmark.status == "failed"
        else "needs_qualification"
    )
    attempts = _usage(db, organization_id=organization_id, now=occurred_at)
    return {
        "state": state,
        "capability": CAPABILITY,
        "customer_label": "Saved-evidence questions",
        "latest_benchmark": _serialize_benchmark(benchmark) if benchmark else None,
        "current": _serialize_event(current) if current else None,
        "routing_enabled": active_here,
        "traffic_percentage": TRAFFIC_PERCENTAGE if active_here else 0,
        "max_prompts_per_day": SHARED_DAILY_PROMPT_LIMIT,
        "daily_limit_shared_with_explanations": True,
        "customer_prompts_allowed": active_here,
        "automatic_rollback_enabled": True,
        "automatic_activation_allowed": False,
        "automatic_changes_allowed": False,
        "usage": attempts,
        "truth": {"state": state, "summary": _summary(state)},
    }


def run_question_capability_benchmark(
    db: Session,
    *,
    organization_id: str,
    connection_id: str,
    actor_user_id: str,
    client_request_id: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    _require_capability_tables(db)
    require_commercial_feature(
        db,
        organization_id=organization_id,
        feature_code=FEATURE_PRIVATE_AI_PROVIDER,
    )
    request_id = _request_id(client_request_id)
    occurred_at = _as_utc(now or datetime.now(UTC))
    organization = _locked_organization(db, organization_id=organization_id)
    connection = _connection(db, organization_id=organization_id, connection_id=connection_id)
    health = _current_eligible_health(
        db,
        organization_id=organization_id,
        connection_id=connection_id,
        now=occurred_at,
    )
    idempotency_key = _hash(
        {"organization_id": organization_id, "request_id": request_id, "kind": "question_benchmark"}
    )
    existing = (
        db.query(GovernedAIProviderCapabilityBenchmark)
        .filter(
            GovernedAIProviderCapabilityBenchmark.organization_id == organization_id,
            GovernedAIProviderCapabilityBenchmark.idempotency_key == idempotency_key,
        )
        .one_or_none()
    )
    if existing is not None:
        if existing.connection_id != connection_id:
            raise _error(
                "This request identifier was already used differently.",
                "ai_provider_capability_request_conflict",
                409,
            )
        return _benchmark_response(db, existing, created=False, now=occurred_at)

    context = {
        "customer_question": _SYNTHETIC_QUESTION,
        "allowed_evidence_ids": [_SYNTHETIC_EVIDENCE_ID],
        "allowed_actions": [{"action_id": _SYNTHETIC_ACTION_ID}],
        "facts": {
            "saved_action": {
                "evidence_id": _SYNTHETIC_EVIDENCE_ID,
                "action_id": _SYNTHETIC_ACTION_ID,
                "summary": "Review the saved website title recommendation.",
            }
        },
        "answer_rules": {
            "authority": "synthetic_evidence_only",
            "may_create_actions": False,
            "may_execute_changes": False,
        },
    }
    started = perf_counter()
    status = "passed"
    reason_code = "ai_provider_question_capability_passed"
    input_tokens = 0
    output_tokens = 0
    try:
        with open_pinned_runtime_provider(
            db,
            organization_id=organization_id,
            connection_id=connection_id,
            timeout_seconds=10,
            max_output_tokens=800,
        ) as provider:
            response = provider.answer_question(
                context=context,
                output_schema=GovernedEvidenceAnswer.model_json_schema(),
                prompt_template_version="insightos-capability-question-check-v1",
            )
            input_tokens = max(0, response.input_tokens)
            output_tokens = max(0, response.output_tokens)
            answer = GovernedEvidenceAnswer.model_validate(response.payload)
            answer.validate_against_context(
                original_question=_SYNTHETIC_QUESTION,
                evidence_ids={_SYNTHETIC_EVIDENCE_ID},
                allowed_action_ids={_SYNTHETIC_ACTION_ID},
            )
            if answer.answer_state != "answered":
                raise ValueError("The synthetic saved evidence was not answered.")
    except GovernedAIProviderConnectionError as exc:
        status = "failed"
        reason_code = exc.reason_code[:120]
    except GovernedAIProviderError as exc:
        status = "failed"
        reason_code = exc.code[:120]
    except (TypeError, ValueError):
        status = "failed"
        reason_code = "ai_provider_question_capability_invalid_output"
    except Exception:
        status = "failed"
        reason_code = "ai_provider_question_capability_unexpected_error"
    latency_ms = min(60_000, max(0, int((perf_counter() - started) * 1000)))
    artifact = {
        "connection_id": connection_id,
        "health_snapshot_id": health.id,
        "capability": CAPABILITY,
        "schema_version": CAPABILITY_SCHEMA_VERSION,
        "status": status,
        "reason_code": reason_code,
        "latency_ms": latency_ms,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "health_artifact_hash": health.artifact_hash,
        "connection_evidence_hash": connection.validation_evidence_hash,
    }
    row = GovernedAIProviderCapabilityBenchmark(
        tenant_id=organization_id,
        organization_id=organization_id,
        connection_id=connection_id,
        health_snapshot_id=health.id,
        capability=CAPABILITY,
        schema_version=CAPABILITY_SCHEMA_VERSION,
        status=status,
        reason_code=reason_code,
        case_count=1,
        latency_ms=latency_ms,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        customer_prompt_sent=False,
        routing_enabled=False,
        automatic_activation_allowed=False,
        automatic_changes_allowed=False,
        health_artifact_hash=health.artifact_hash,
        connection_evidence_hash=str(connection.validation_evidence_hash),
        artifact_hash=_hash(artifact),
        idempotency_key=idempotency_key,
        created_by_user_id=actor_user_id,
        created_at=occurred_at,
    )
    db.add(row)
    write_audit_log(
        db,
        tenant_id=organization.id,
        actor_user_id=actor_user_id,
        event_type="ai.provider_capability.question_benchmark_created",
        payload={
            "connection_id": connection_id,
            "benchmark_id": row.id,
            "capability": CAPABILITY,
            "status": status,
            "reason_code": reason_code,
            "customer_prompt_sent": False,
            "routing_enabled": False,
        },
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        repeated = (
            db.query(GovernedAIProviderCapabilityBenchmark)
            .filter(
                GovernedAIProviderCapabilityBenchmark.organization_id == organization_id,
                GovernedAIProviderCapabilityBenchmark.idempotency_key == idempotency_key,
            )
            .one()
        )
        return _benchmark_response(db, repeated, created=False, now=occurred_at)
    db.refresh(row)
    return _benchmark_response(db, row, created=True, now=occurred_at)


def set_question_capability(
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
    _require_capability_tables(db)
    if action not in {"enable", "disable"}:
        raise _error("Choose enable or disable.", "ai_provider_capability_action_invalid", 422)
    if action == "enable":
        require_commercial_feature(
            db,
            organization_id=organization_id,
            feature_code=FEATURE_PRIVATE_AI_PROVIDER,
        )
    request_id = _request_id(client_request_id)
    occurred_at = _as_utc(now or datetime.now(UTC))
    organization = _locked_organization(db, organization_id=organization_id)
    connection = _connection(db, organization_id=organization_id, connection_id=connection_id)
    idempotency_key = _hash(
        {"organization_id": organization_id, "request_id": request_id, "kind": "question_event"}
    )
    existing = (
        db.query(GovernedAIProviderCapabilityEvent)
        .filter(
            GovernedAIProviderCapabilityEvent.organization_id == organization_id,
            GovernedAIProviderCapabilityEvent.idempotency_key == idempotency_key,
        )
        .one_or_none()
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
                "Confirm every saved-question capability acknowledgement.",
                "ai_provider_capability_acknowledgement_required",
                422,
            )
        if current is not None and current.action == "enabled":
            raise _error(
                "Stop the current capability check before starting another one.",
                "ai_provider_capability_already_enabled",
                409,
            )
        benchmark = _latest_benchmark(
            db,
            organization_id=organization_id,
            connection_id=connection_id,
        )
        if not _benchmark_current(
            db,
            benchmark=benchmark,
            connection=connection,
            now=occurred_at,
        ):
            raise _error(
                "Run the saved-question compatibility check again before enabling it.",
                "ai_provider_capability_benchmark_required",
                409,
            )
        assert benchmark is not None
        health = db.get(GovernedAIProviderCanaryHealthSnapshot, benchmark.health_snapshot_id)
        if health is None:
            raise _error(
                "The private-AI health evidence is unavailable.",
                "ai_provider_capability_health_required",
                409,
            )
        row_action = "enabled"
        state = "capability_canary"
        traffic = TRAFFIC_PERCENTAGE
        prompts = True
        reason = "ai_provider_question_capability_owner_enabled"
        ack_payload = {key: True for key in _ACKS}
    else:
        if current is None or current.action != "enabled" or current.connection_id != connection_id:
            raise _error(
                "This saved-question capability is not active.",
                "ai_provider_capability_not_enabled",
                409,
            )
        benchmark = db.get(GovernedAIProviderCapabilityBenchmark, current.benchmark_id)
        health = db.get(GovernedAIProviderCanaryHealthSnapshot, current.health_snapshot_id)
        if benchmark is None or health is None:
            raise _error(
                "The capability evidence is unavailable.",
                "ai_provider_capability_evidence_required",
                409,
            )
        row_action = "disabled"
        state = "inactive"
        traffic = 0
        prompts = False
        reason = "ai_provider_question_capability_owner_disabled"
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
        event_type=f"ai.provider_capability.question_{row_action}",
        payload={
            "connection_id": connection_id,
            "capability_event_id": row.id,
            "capability": CAPABILITY,
            "traffic_percentage": traffic,
            "shared_daily_prompt_limit": SHARED_DAILY_PROMPT_LIMIT,
            "automatic_changes_allowed": False,
        },
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        repeated = (
            db.query(GovernedAIProviderCapabilityEvent)
            .filter(
                GovernedAIProviderCapabilityEvent.organization_id == organization_id,
                GovernedAIProviderCapabilityEvent.idempotency_key == idempotency_key,
            )
            .one()
        )
        return _event_response(db, repeated, created=False, now=occurred_at)
    db.refresh(row)
    return _event_response(db, row, created=True, now=occurred_at)


def select_question_capability(
    db: Session,
    *,
    organization_id: str,
    request_key: str,
    now: datetime | None = None,
) -> CapabilitySelection | None:
    if not _capability_tables_available(db):
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
    if connection is None or not _event_current(
        db,
        event=event,
        connection=connection,
        now=occurred_at,
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


def authorize_question_dispatch(
    db: Session,
    *,
    organization_id: str,
    selection: CapabilitySelection,
    now: datetime | None = None,
) -> GovernedAIProviderCapabilityEvent:
    _require_capability_tables(db)
    occurred_at = _as_utc(now or datetime.now(UTC))
    _locked_organization(db, organization_id=organization_id)
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
        or not _event_current(db, event=event, connection=connection, now=occurred_at)
    ):
        raise _error(
            "The saved-question private-AI capability is no longer authorized.",
            "ai_provider_capability_not_current",
            409,
        )
    if _shared_daily_attempts(db, organization_id=organization_id, now=occurred_at) >= 1:
        raise _error(
            "The shared private-AI check has reached today's one-prompt limit.",
            "ai_provider_shared_daily_limit",
            409,
        )
    return event


def automatic_capability_rollback(
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
            {"event_id": event.id, "reason_code": reason_code, "kind": "capability_rollback"}
        ),
        actor_user_id=None,
        now=occurred_at,
    )
    db.add(rollback)
    write_audit_log(
        db,
        tenant_id=event.organization_id,
        actor_user_id=None,
        event_type="ai.provider_capability.question_automatic_rollback",
        payload={
            "connection_id": event.connection_id,
            "previous_event_id": event.id,
            "capability_event_id": rollback.id,
            "reason_code": reason_code[:120],
            "traffic_percentage": 0,
            "managed_fallback_required": True,
        },
    )
    db.commit()
    db.refresh(rollback)
    return rollback


def record_capability_success(
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


def record_capability_fallback(
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
        outcome="managed_fallback_succeeded" if managed_succeeded else "managed_fallback_failed",
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
        artifact_hash=_hash(artifact),
        created_at=occurred_at,
    )
    db.add(row)
    write_audit_log(
        db,
        tenant_id=event.organization_id,
        actor_user_id=None,
        event_type=f"ai.provider_capability.question_attempt.{outcome}",
        payload={
            "connection_id": event.connection_id,
            "capability_event_id": event.id,
            "attempt_id": row.id,
            "outcome": outcome,
            "managed_fallback_used": managed_fallback_used,
            "automatic_rollback_triggered": automatic_rollback_triggered,
            "automatic_changes_allowed": False,
        },
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return (
            db.query(GovernedAIProviderCapabilityAttempt)
            .filter(
                GovernedAIProviderCapabilityAttempt.organization_id == event.organization_id,
                GovernedAIProviderCapabilityAttempt.request_key_hash == request_hash,
            )
            .one()
        )
    db.refresh(row)
    return row


def _current_eligible_health(
    db: Session,
    *,
    organization_id: str,
    connection_id: str,
    now: datetime,
) -> GovernedAIProviderCanaryHealthSnapshot:
    health = (
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
    monitoring = list_canary_monitoring(
        db,
        organization_id=organization_id,
        connection_id=connection_id,
        now=now,
    )
    if (
        health is None
        or health.status != "eligible_for_later_review"
        or monitoring["state"] != "eligible_for_later_review"
        or monitoring["latest"] is None
        or monitoring["latest"]["id"] != health.id
    ):
        raise _error(
            "Collect and save the minimum private-AI health evidence first.",
            "ai_provider_capability_health_required",
            409,
        )
    return health


def _benchmark_current(
    db: Session,
    *,
    benchmark: GovernedAIProviderCapabilityBenchmark | None,
    connection: GovernedAIProviderConnection,
    now: datetime,
) -> bool:
    if (
        benchmark is None
        or benchmark.status != "passed"
        or benchmark.capability != CAPABILITY
        or benchmark.connection_evidence_hash != connection.validation_evidence_hash
    ):
        return False
    try:
        health = _current_eligible_health(
            db,
            organization_id=connection.organization_id,
            connection_id=connection.id,
            now=now,
        )
    except (GovernedAIProviderConnectionError, CostEconomicsError):
        return False
    return bool(
        benchmark.health_snapshot_id == health.id
        and benchmark.health_artifact_hash == health.artifact_hash
    )


def _event_current(
    db: Session,
    *,
    event: GovernedAIProviderCapabilityEvent,
    connection: GovernedAIProviderConnection,
    now: datetime,
) -> bool:
    if not _private_ai_allowed(db, organization_id=event.organization_id):
        return False
    base = list_provider_canary(
        db,
        organization_id=event.organization_id,
        connection_id=event.connection_id,
        now=now,
    )
    benchmark = db.get(GovernedAIProviderCapabilityBenchmark, event.benchmark_id)
    return bool(
        base["state"] == "canary"
        and benchmark is not None
        and benchmark.id == event.benchmark_id
        and benchmark.health_snapshot_id == event.health_snapshot_id
        and _benchmark_current(db, benchmark=benchmark, connection=connection, now=now)
    )


def _private_ai_allowed(db: Session, *, organization_id: str) -> bool:
    try:
        require_commercial_feature(
            db,
            organization_id=organization_id,
            feature_code=FEATURE_PRIVATE_AI_PROVIDER,
        )
    except CostEconomicsError:
        return False
    return True


def _shared_daily_attempts(db: Session, *, organization_id: str, now: datetime) -> int:
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    base_count = (
        db.query(GovernedAIProviderCanaryAttempt)
        .filter(
            GovernedAIProviderCanaryAttempt.organization_id == organization_id,
            GovernedAIProviderCanaryAttempt.created_at >= day_start,
        )
        .count()
    )
    capability_count = (
        db.query(GovernedAIProviderCapabilityAttempt)
        .filter(
            GovernedAIProviderCapabilityAttempt.organization_id == organization_id,
            GovernedAIProviderCapabilityAttempt.created_at >= day_start,
        )
        .count()
    )
    return base_count + capability_count


def _capability_tables_available(db: Session) -> bool:
    inspector = inspect(db.get_bind())
    return all(
        inspector.has_table(table)
        for table in (
            GovernedAIProviderCapabilityBenchmark.__tablename__,
            GovernedAIProviderCapabilityEvent.__tablename__,
            GovernedAIProviderCapabilityAttempt.__tablename__,
        )
    )


def _require_capability_tables(db: Session) -> None:
    if not _capability_tables_available(db):
        raise _error(
            "Saved-question private AI is not available yet.",
            "ai_provider_question_capability_unavailable",
            409,
        )


def _unavailable_capability() -> dict[str, Any]:
    state = "unavailable"
    return {
        "state": state,
        "capability": CAPABILITY,
        "customer_label": "Saved-evidence questions",
        "latest_benchmark": None,
        "current": None,
        "routing_enabled": False,
        "traffic_percentage": 0,
        "max_prompts_per_day": SHARED_DAILY_PROMPT_LIMIT,
        "daily_limit_shared_with_explanations": True,
        "customer_prompts_allowed": False,
        "automatic_rollback_enabled": True,
        "automatic_activation_allowed": False,
        "automatic_changes_allowed": False,
        "usage": {
            "window_days": 30,
            "private_attempts": 0,
            "private_successes": 0,
            "managed_fallbacks": 0,
            "automatic_rollbacks": 0,
        },
        "truth": {
            "state": state,
            "summary": "Saved-question private AI is not available yet.",
        },
    }


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


def _latest_benchmark(
    db: Session,
    *,
    organization_id: str,
    connection_id: str,
) -> GovernedAIProviderCapabilityBenchmark | None:
    return (
        db.query(GovernedAIProviderCapabilityBenchmark)
        .filter(
            GovernedAIProviderCapabilityBenchmark.organization_id == organization_id,
            GovernedAIProviderCapabilityBenchmark.connection_id == connection_id,
            GovernedAIProviderCapabilityBenchmark.capability == CAPABILITY,
        )
        .order_by(
            GovernedAIProviderCapabilityBenchmark.created_at.desc(),
            GovernedAIProviderCapabilityBenchmark.id.desc(),
        )
        .first()
    )


def _latest_event(db: Session, *, organization_id: str) -> GovernedAIProviderCapabilityEvent | None:
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


def _connection(
    db: Session,
    *,
    organization_id: str,
    connection_id: str,
) -> GovernedAIProviderConnection:
    row = _connection_or_none(db, organization_id=organization_id, connection_id=connection_id)
    if row is None:
        raise _error("Private AI provider not found.", "ai_provider_connection_not_found", 404)
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


def _locked_organization(db: Session, *, organization_id: str) -> Organization:
    row = (
        db.query(Organization)
        .filter(Organization.id == organization_id)
        .populate_existing()
        .with_for_update()
        .one_or_none()
    )
    if row is None:
        raise _error("Organization not found.", "organization_not_found", 404)
    return row


def _usage(db: Session, *, organization_id: str, now: datetime) -> dict[str, int]:
    start = now - timedelta(days=30)
    rows = (
        db.query(GovernedAIProviderCapabilityAttempt)
        .filter(
            GovernedAIProviderCapabilityAttempt.organization_id == organization_id,
            GovernedAIProviderCapabilityAttempt.capability == CAPABILITY,
            GovernedAIProviderCapabilityAttempt.created_at >= start,
        )
        .all()
    )
    return {
        "window_days": 30,
        "private_attempts": len(rows),
        "private_successes": sum(row.outcome == "private_succeeded" for row in rows),
        "managed_fallbacks": sum(row.managed_fallback_used for row in rows),
        "automatic_rollbacks": sum(row.automatic_rollback_triggered for row in rows),
    }


def _serialize_benchmark(
    row: GovernedAIProviderCapabilityBenchmark,
) -> dict[str, Any]:
    return {
        "id": row.id,
        "capability": row.capability,
        "status": row.status,
        "reason_code": row.reason_code,
        "case_count": row.case_count,
        "latency_ms": row.latency_ms,
        "input_tokens": row.input_tokens,
        "output_tokens": row.output_tokens,
        "customer_prompt_sent": False,
        "routing_enabled": False,
        "automatic_activation_allowed": False,
        "automatic_changes_allowed": False,
        "created_at": row.created_at.isoformat(),
        "immutable": True,
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
        "reason_code": row.reason_code,
        "created_at": row.created_at.isoformat(),
        "immutable": True,
    }


def _benchmark_response(
    db: Session,
    row: GovernedAIProviderCapabilityBenchmark,
    *,
    created: bool,
    now: datetime,
) -> dict[str, Any]:
    return {
        "created": created,
        "item": _serialize_benchmark(row),
        **list_question_capability(
            db,
            organization_id=row.organization_id,
            connection_id=row.connection_id,
            now=now,
        ),
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
        **list_question_capability(
            db,
            organization_id=row.organization_id,
            connection_id=row.connection_id,
            now=now,
        ),
    }


def _summary(state: str) -> str:
    if state == "capability_canary":
        return "A fixed 5% check may answer saved-evidence questions, within the shared one-prompt daily limit."
    if state == "eligible_for_owner_approval":
        return "The saved-question compatibility check passed and is ready for explicit owner review."
    if state == "needs_attention":
        return "The saved-question capability is paused because its evidence is no longer current."
    if state == "qualification_failed":
        return "The saved-question compatibility check did not pass."
    if state == "capability_canary_elsewhere":
        return "Another private provider already owns the saved-question capability check."
    return "Run a synthetic saved-question compatibility check before owner review."


def _request_id(value: str) -> str:
    normalized = value.strip()
    if len(normalized) < 8 or len(normalized) > 64:
        raise _error(
            "The request identifier is invalid.",
            "ai_provider_capability_request_invalid",
            422,
        )
    return normalized


def _hash(payload: dict[str, Any]) -> str:
    return sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


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

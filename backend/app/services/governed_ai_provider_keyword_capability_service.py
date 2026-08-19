from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256
from time import perf_counter
from typing import Any

from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.intelligence.contracts.governed_ai import GovernedKeywordRelevanceReview
from app.models.governed_ai_provider_capability import (
    GovernedAIProviderCapabilityAttempt,
    GovernedAIProviderCapabilityBenchmark,
    GovernedAIProviderCapabilityEvent,
)
from app.models.governed_ai_provider_canary import (
    GovernedAIProviderCanaryHealthSnapshot,
)
from app.models.governed_ai_provider_connection import GovernedAIProviderConnection
from app.services.audit_service import write_audit_log
from app.services.commercial_plan_service import (
    FEATURE_PRIVATE_AI_PROVIDER,
    require_commercial_feature,
)
from app.services.cost_economics_service import CostEconomicsError
from app.services.governed_ai_provider import GovernedAIProviderError
from app.services.governed_ai_provider_capability_service import (
    CapabilitySelection,
    SHARED_DAILY_PROMPT_LIMIT,
    TRAFFIC_PERCENTAGE,
    _as_utc,
    _capability_tables_available,
    _connection,
    _connection_or_none,
    _current_eligible_health,
    _error,
    _hash,
    _locked_organization,
    _private_ai_allowed,
    _request_id,
    _shared_daily_attempts,
)
from app.services.governed_ai_provider_canary_service import list_provider_canary
from app.services.governed_ai_provider_connection_service import (
    GovernedAIProviderConnectionError,
    open_pinned_runtime_provider,
)


CAPABILITY = "keyword_relevance_review"
CAPABILITY_SCHEMA_VERSION = "governed-keyword-relevance-review-v1"
PROMPT_TEMPLATE_VERSION = "insightos-capability-keyword-review-check-v1"
_SYNTHETIC_SUGGESTION_ID = "synthetic-search-1"
_SYNTHETIC_SERVICE_ID = "synthetic-service-1"
_SYNTHETIC_AREA_ID = "synthetic-area-1"
_SYNTHETIC_EVIDENCE_IDS = {
    f"search:{_SYNTHETIC_SUGGESTION_ID}",
    f"service:{_SYNTHETIC_SERVICE_ID}",
    f"area:{_SYNTHETIC_AREA_ID}",
}
_ACKS = (
    "reviewed_keyword_review_check",
    "understands_real_saved_search_context",
    "understands_shared_daily_limit",
    "understands_managed_fallback_and_rollback",
    "understands_saved_search_classification_only",
)


def list_keyword_review_qualification(
    db: Session,
    *,
    organization_id: str,
    connection_id: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    occurred_at = _as_utc(now or datetime.now(UTC))
    connection = _connection(
        db, organization_id=organization_id, connection_id=connection_id
    )
    if not _keyword_review_qualification_schema_available(db):
        return _unavailable_qualification()
    benchmark = _latest_benchmark(
        db, organization_id=organization_id, connection_id=connection_id
    )
    benchmark_current = _benchmark_current(
        db, benchmark=benchmark, connection=connection, now=occurred_at
    )
    runtime_available = _keyword_review_runtime_schema_available(db)
    current = (
        _latest_event(db, organization_id=organization_id)
        if runtime_available
        else None
    )
    recorded_here = bool(
        current and current.action == "enabled" and current.connection_id == connection_id
    )
    active_here = bool(
        recorded_here
        and _event_current(db, event=current, connection=connection, now=occurred_at)
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
        if benchmark_current and runtime_available
        else "eligible_for_later_review"
        if benchmark_current
        else "qualification_failed"
        if benchmark is not None and benchmark.status == "failed"
        else "needs_attention"
        if benchmark is not None
        else "needs_qualification"
    )
    return {
        "state": state,
        "capability": CAPABILITY,
        "customer_label": "Unclear search review",
        "latest_benchmark": _serialize_benchmark(benchmark) if benchmark else None,
        "current": _serialize_event(current) if current else None,
        "routing_enabled": active_here,
        "traffic_percentage": TRAFFIC_PERCENTAGE if active_here else 0,
        "max_prompts_per_day": SHARED_DAILY_PROMPT_LIMIT,
        "daily_limit_shared_with_explanations_questions_and_drafts": True,
        "customer_prompts_allowed": active_here,
        "owner_activation_available": bool(benchmark_current and runtime_available),
        "automatic_activation_allowed": False,
        "automatic_changes_allowed": False,
        "saved_searches_changed": False,
        "classification_only": True,
        "may_update_reviewed_saved_searches": active_here,
        "may_add_or_track_searches": False,
        "publishing_allowed": False,
        "automatic_rollback_enabled": True,
        "usage": _usage(db, organization_id=organization_id, now=occurred_at),
        "qualification_only": not runtime_available,
        "truth": {"state": state, "summary": _summary(state)},
    }


def run_keyword_review_qualification(
    db: Session,
    *,
    organization_id: str,
    connection_id: str,
    actor_user_id: str,
    client_request_id: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    _require_qualification_schema(db)
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
    health = _current_eligible_health(
        db,
        organization_id=organization_id,
        connection_id=connection_id,
        now=occurred_at,
    )
    idempotency_key = _hash(
        {
            "organization_id": organization_id,
            "request_id": request_id,
            "kind": "keyword_review_capability_benchmark",
        }
    )
    existing = _benchmark_by_idempotency(
        db, organization_id=organization_id, idempotency_key=idempotency_key
    )
    if existing is not None:
        if existing.connection_id != connection_id or existing.capability != CAPABILITY:
            raise _error(
                "This request identifier was already used differently.",
                "ai_provider_capability_request_conflict",
                409,
            )
        return _benchmark_response(db, existing, created=False, now=occurred_at)

    context = _synthetic_context()
    started = perf_counter()
    status = "passed"
    reason_code = "ai_provider_keyword_review_qualification_passed"
    input_tokens = 0
    output_tokens = 0
    try:
        with open_pinned_runtime_provider(
            db,
            organization_id=organization_id,
            connection_id=connection_id,
            timeout_seconds=10,
            max_output_tokens=1_200,
        ) as provider:
            response = provider.review_keyword_relevance(
                context=context,
                output_schema=GovernedKeywordRelevanceReview.model_json_schema(),
                prompt_template_version=PROMPT_TEMPLATE_VERSION,
            )
            input_tokens = max(0, response.input_tokens)
            output_tokens = max(0, response.output_tokens)
            review = GovernedKeywordRelevanceReview.model_validate(response.payload)
            review.validate_against_context(
                suggestion_ids={_SYNTHETIC_SUGGESTION_ID},
                service_ids={_SYNTHETIC_SERVICE_ID},
                included_area_ids={_SYNTHETIC_AREA_ID},
                excluded_area_ids=set(),
                evidence_ids=_SYNTHETIC_EVIDENCE_IDS,
            )
            decision = review.decisions[0]
            if (
                decision.classification != "relevant"
                or decision.confidence < 0.8
                or decision.matched_service_id != _SYNTHETIC_SERVICE_ID
                or decision.matched_service_area_id != _SYNTHETIC_AREA_ID
                or decision.area_basis != "included_area"
                or set(decision.evidence_used) != _SYNTHETIC_EVIDENCE_IDS
            ):
                raise ValueError("The synthetic search was not classified correctly.")
    except GovernedAIProviderConnectionError as exc:
        status = "failed"
        reason_code = exc.reason_code[:120]
    except GovernedAIProviderError as exc:
        status = "failed"
        reason_code = exc.code[:120]
    except (TypeError, ValueError):
        status = "failed"
        reason_code = "ai_provider_keyword_review_qualification_invalid_output"
    except Exception:
        status = "failed"
        reason_code = "ai_provider_keyword_review_qualification_unexpected_error"
    latency_ms = min(60_000, max(0, int((perf_counter() - started) * 1_000)))
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
        "customer_prompt_sent": False,
        "routing_enabled": False,
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
        event_type="ai.provider_capability.keyword_review_qualification_created",
        payload={
            "connection_id": connection_id,
            "benchmark_id": row.id,
            "capability": CAPABILITY,
            "status": status,
            "reason_code": reason_code,
            "customer_prompt_sent": False,
            "routing_enabled": False,
            "saved_searches_changed": False,
        },
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        repeated = _benchmark_by_idempotency(
            db, organization_id=organization_id, idempotency_key=idempotency_key
        )
        assert repeated is not None
        return _benchmark_response(db, repeated, created=False, now=occurred_at)
    db.refresh(row)
    return _benchmark_response(db, row, created=True, now=occurred_at)


def set_keyword_review_capability(
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
            "kind": "keyword_review_capability_event",
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
                "Confirm every unclear-search review acknowledgement.",
                "ai_provider_keyword_review_acknowledgement_required",
                422,
            )
        if current is not None and current.action == "enabled":
            raise _error(
                "Stop the current unclear-search check before starting another one.",
                "ai_provider_keyword_review_already_enabled",
                409,
            )
        benchmark = _latest_benchmark(
            db, organization_id=organization_id, connection_id=connection_id
        )
        if not _benchmark_current(
            db, benchmark=benchmark, connection=connection, now=occurred_at
        ):
            raise _error(
                "Run the unclear-search compatibility check again before enabling it.",
                "ai_provider_keyword_review_benchmark_required",
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
        row_action = "enabled"
        state = "capability_canary"
        traffic = TRAFFIC_PERCENTAGE
        prompts = True
        reason = "ai_provider_keyword_review_owner_enabled"
        ack_payload = {key: True for key in _ACKS}
    else:
        if (
            current is None
            or current.action != "enabled"
            or current.connection_id != connection_id
        ):
            raise _error(
                "This unclear-search capability is not active.",
                "ai_provider_keyword_review_not_enabled",
                409,
            )
        benchmark = db.get(
            GovernedAIProviderCapabilityBenchmark, current.benchmark_id
        )
        health = db.get(
            GovernedAIProviderCanaryHealthSnapshot, current.health_snapshot_id
        )
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
        reason = "ai_provider_keyword_review_owner_disabled"
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
        event_type=f"ai.provider_capability.keyword_review_{row_action}",
        payload={
            "connection_id": connection_id,
            "capability_event_id": row.id,
            "capability": CAPABILITY,
            "traffic_percentage": traffic,
            "shared_daily_prompt_limit": SHARED_DAILY_PROMPT_LIMIT,
            "classification_only": True,
            "may_add_or_track_searches": False,
            "automatic_changes_allowed": False,
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


def select_keyword_review_capability(
    db: Session,
    *,
    organization_id: str,
    request_key: str,
    now: datetime | None = None,
) -> CapabilitySelection | None:
    if not _keyword_review_runtime_schema_available(db):
        return None
    occurred_at = _as_utc(now or datetime.now(UTC))
    event = _latest_event(db, organization_id=organization_id)
    if event is None or event.action != "enabled":
        return None
    connection = _connection_or_none(
        db, organization_id=organization_id, connection_id=event.connection_id
    )
    if connection is None or not _event_current(
        db, event=event, connection=connection, now=occurred_at
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


def authorize_keyword_review_dispatch(
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
    connection = _connection_or_none(
        db, organization_id=organization_id, connection_id=selection.connection_id
    )
    if (
        event is None
        or event.id != selection.event_id
        or event.action != "enabled"
        or connection is None
        or not _event_current(db, event=event, connection=connection, now=occurred_at)
    ):
        raise _error(
            "The unclear-search private-AI capability is no longer authorized.",
            "ai_provider_keyword_review_not_current",
            409,
        )
    if _shared_daily_attempts(db, organization_id=organization_id, now=occurred_at) >= 1:
        raise _error(
            "The shared private-AI check has reached today's one-prompt limit.",
            "ai_provider_shared_daily_limit",
            409,
        )
    return event


def automatic_keyword_review_rollback(
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
    health = db.get(
        GovernedAIProviderCanaryHealthSnapshot, event.health_snapshot_id
    )
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
                "kind": "keyword_review_capability_rollback",
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
        event_type="ai.provider_capability.keyword_review_automatic_rollback",
        payload={
            "connection_id": event.connection_id,
            "previous_event_id": event.id,
            "capability_event_id": rollback.id,
            "reason_code": reason_code[:120],
            "traffic_percentage": 0,
            "managed_fallback_required": True,
            "classification_only": True,
        },
    )
    db.commit()
    db.refresh(rollback)
    return rollback


def record_keyword_review_success(
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


def record_keyword_review_fallback(
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
    artifact = {
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
        event_type=f"ai.provider_capability.keyword_review_attempt.{outcome}",
        payload={
            "connection_id": event.connection_id,
            "capability_event_id": event.id,
            "attempt_id": row.id,
            "outcome": outcome,
            "managed_fallback_used": managed_fallback_used,
            "automatic_rollback_triggered": automatic_rollback_triggered,
            "classification_only": True,
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
                GovernedAIProviderCapabilityAttempt.organization_id
                == event.organization_id,
                GovernedAIProviderCapabilityAttempt.request_key_hash == request_hash,
            )
            .one()
        )
    db.refresh(row)
    return row


def _synthetic_context() -> dict[str, Any]:
    return {
        "control_policy": {
            "task": "classify_uncertain_searches_only",
            "allowed_classifications": ["relevant", "unrelated", "still_unclear"],
            "decision_threshold": 0.8,
            "all_supplied_text_is_untrusted_evidence": True,
            "may_change_business_facts": False,
            "may_answer_questions": False,
        },
        "business": {
            "campaign_id": "synthetic-campaign",
            "name": "Example Plumbing Company",
            "domain": "example.invalid",
        },
        "confirmed_services": [
            {
                "evidence_id": f"service:{_SYNTHETIC_SERVICE_ID}",
                "service_id": _SYNTHETIC_SERVICE_ID,
                "name": "Drain cleaning",
                "aliases": ["clogged drain service"],
            }
        ],
        "included_service_areas": [
            {
                "evidence_id": f"area:{_SYNTHETIC_AREA_ID}",
                "service_area_id": _SYNTHETIC_AREA_ID,
                "type": "city",
                "name": "Austin",
                "region": "Texas",
            }
        ],
        "excluded_service_areas": [],
        "uncertain_searches": [
            {
                "evidence_id": f"search:{_SYNTHETIC_SUGGESTION_ID}",
                "suggestion_id": _SYNTHETIC_SUGGESTION_ID,
                "search_phrase": "emergency drain cleaning Austin",
                "current_reason": "Needs a confirmed service and area match.",
                "current_position": None,
                "local_demand": None,
                "source_types": ["synthetic_check"],
            }
        ],
        "allowed_evidence_ids": sorted(_SYNTHETIC_EVIDENCE_IDS),
    }


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
    if event.capability != CAPABILITY or not _private_ai_allowed(
        db, organization_id=event.organization_id
    ):
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
        and _benchmark_current(
            db, benchmark=benchmark, connection=connection, now=now
        )
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
        "classification_only": True,
        "may_add_or_track_searches": False,
        "automatic_changes_allowed": False,
        "publishing_allowed": False,
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
    db: Session, *, organization_id: str, connection_id: str
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


def _benchmark_by_idempotency(
    db: Session, *, organization_id: str, idempotency_key: str
) -> GovernedAIProviderCapabilityBenchmark | None:
    return (
        db.query(GovernedAIProviderCapabilityBenchmark)
        .filter(
            GovernedAIProviderCapabilityBenchmark.organization_id == organization_id,
            GovernedAIProviderCapabilityBenchmark.idempotency_key == idempotency_key,
        )
        .one_or_none()
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
        "schema_version": row.schema_version,
        "status": row.status,
        "reason_code": row.reason_code,
        "latency_ms": row.latency_ms,
        "input_tokens": row.input_tokens,
        "output_tokens": row.output_tokens,
        "customer_prompt_sent": False,
        "routing_enabled": False,
        "automatic_activation_allowed": False,
        "automatic_changes_allowed": False,
        "saved_searches_changed": False,
        "created_at": _as_utc(row.created_at).isoformat(),
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
        "automatic_changes_allowed": False,
        "classification_only": True,
        "may_add_or_track_searches": False,
        "publishing_allowed": False,
        "reason_code": row.reason_code,
        "created_at": _as_utc(row.created_at).isoformat(),
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
        **list_keyword_review_qualification(
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
        **list_keyword_review_qualification(
            db,
            organization_id=row.organization_id,
            connection_id=row.connection_id,
            now=now,
        ),
    }


def _require_qualification_schema(db: Session) -> None:
    if not _keyword_review_qualification_schema_available(db):
        raise _error(
            "Unclear-search private AI is not available yet.",
            "ai_provider_keyword_review_qualification_unavailable",
            409,
        )


def _require_runtime_schema(db: Session) -> None:
    if not _keyword_review_runtime_schema_available(db):
        raise _error(
            "Unclear-search private-AI routing is not available yet.",
            "ai_provider_keyword_review_runtime_unavailable",
            409,
        )


def _keyword_review_qualification_schema_available(db: Session) -> bool:
    if not _capability_tables_available(db):
        return False
    try:
        constraints = inspect(db.get_bind()).get_check_constraints(
            GovernedAIProviderCapabilityBenchmark.__tablename__
        )
    except Exception:
        return False
    return any(
        CAPABILITY in str(item.get("sqltext") or "") for item in constraints
    )


def _keyword_review_runtime_schema_available(db: Session) -> bool:
    if not _keyword_review_qualification_schema_available(db):
        return False
    try:
        inspector = inspect(db.get_bind())
        event_constraints = inspector.get_check_constraints(
            GovernedAIProviderCapabilityEvent.__tablename__
        )
        attempt_constraints = inspector.get_check_constraints(
            GovernedAIProviderCapabilityAttempt.__tablename__
        )
    except Exception:
        return False
    return all(
        any(CAPABILITY in str(item.get("sqltext") or "") for item in constraints)
        for constraints in (event_constraints, attempt_constraints)
    )


def _unavailable_qualification() -> dict[str, Any]:
    state = "unavailable"
    return {
        "state": state,
        "capability": CAPABILITY,
        "customer_label": "Unclear search review",
        "latest_benchmark": None,
        "current": None,
        "routing_enabled": False,
        "traffic_percentage": 0,
        "max_prompts_per_day": SHARED_DAILY_PROMPT_LIMIT,
        "daily_limit_shared_with_explanations_questions_and_drafts": True,
        "customer_prompts_allowed": False,
        "owner_activation_available": False,
        "automatic_activation_allowed": False,
        "automatic_changes_allowed": False,
        "saved_searches_changed": False,
        "classification_only": True,
        "may_update_reviewed_saved_searches": False,
        "may_add_or_track_searches": False,
        "publishing_allowed": False,
        "automatic_rollback_enabled": True,
        "usage": {
            "window_days": 30,
            "private_attempts": 0,
            "private_successes": 0,
            "managed_fallbacks": 0,
            "automatic_rollbacks": 0,
        },
        "qualification_only": True,
        "truth": {
            "state": state,
            "summary": "Unclear-search private AI is not available yet.",
        },
    }


def _summary(state: str) -> str:
    if state == "capability_canary":
        return "A fixed 5% unclear-search check is active with managed fallback."
    if state == "eligible_for_owner_approval":
        return "The synthetic unclear-search check passed and is ready for owner review."
    if state == "eligible_for_later_review":
        return (
            "The synthetic unclear-search check passed. Customer traffic remains off "
            "until a separate owner-review sprint is complete."
        )
    if state == "qualification_failed":
        return "The synthetic unclear-search check did not pass; no customer data was sent."
    if state == "needs_attention":
        return "The saved check is no longer current. Refresh health evidence and run it again."
    if state == "capability_canary_elsewhere":
        return "Another private provider owns the limited unclear-search check."
    return "Run the synthetic unclear-search check before considering limited use."

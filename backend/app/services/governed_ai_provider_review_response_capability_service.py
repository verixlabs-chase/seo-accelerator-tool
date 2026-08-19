from __future__ import annotations

from datetime import UTC, datetime
from time import perf_counter
from typing import Any

from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.intelligence.contracts.governed_ai import GovernedActionDraft
from app.models.governed_ai_provider_capability import (
    GovernedAIProviderCapabilityBenchmark,
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
    _as_utc,
    _capability_tables_available,
    _connection,
    _current_eligible_health,
    _error,
    _hash,
    _locked_organization,
    _request_id,
)
from app.services.governed_ai_provider_connection_service import (
    GovernedAIProviderConnectionError,
    open_pinned_runtime_provider,
)


CAPABILITY = "review_response_draft"
CAPABILITY_SCHEMA_VERSION = "governed-review-response-draft-v1"
PROMPT_TEMPLATE_VERSION = "insightos-capability-review-response-check-v1"
_SYNTHETIC_ACTION_ID = "review-response:synthetic-review"
_SYNTHETIC_EVIDENCE_IDS = {
    "review:synthetic-review",
    "location:synthetic-location",
}


def list_review_response_qualification(
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
    if not _qualification_schema_available(db):
        return _unavailable_qualification()
    benchmark = _latest_benchmark(
        db, organization_id=organization_id, connection_id=connection_id
    )
    benchmark_current = _benchmark_current(
        db, benchmark=benchmark, connection=connection, now=occurred_at
    )
    state = (
        "eligible_for_later_review"
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
        "customer_label": "Optional review reply wording",
        "latest_benchmark": _serialize_benchmark(benchmark) if benchmark else None,
        "routing_enabled": False,
        "traffic_percentage": 0,
        "customer_prompts_allowed": False,
        "owner_activation_available": False,
        "automatic_activation_allowed": False,
        "automatic_changes_allowed": False,
        "draft_only": True,
        "customer_review_sent": False,
        "review_status_changed": False,
        "may_post_response": False,
        "publishing_allowed": False,
        "qualification_only": True,
        "truth": {"state": state, "summary": _summary(state)},
    }


def run_review_response_qualification(
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
            "kind": "review_response_capability_benchmark",
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

    started = perf_counter()
    result_status = "passed"
    reason_code = "ai_provider_review_response_qualification_passed"
    input_tokens = 0
    output_tokens = 0
    try:
        with open_pinned_runtime_provider(
            db,
            organization_id=organization_id,
            connection_id=connection_id,
            timeout_seconds=10,
            max_output_tokens=1_000,
        ) as provider:
            response = provider.draft_action(
                context=_synthetic_context(),
                output_schema=GovernedActionDraft.model_json_schema(),
                prompt_template_version=PROMPT_TEMPLATE_VERSION,
            )
            input_tokens = max(0, response.input_tokens)
            output_tokens = max(0, response.output_tokens)
            draft = GovernedActionDraft.model_validate(response.payload)
            draft.validate_against_context(
                requested_action_id=_SYNTHETIC_ACTION_ID,
                requested_draft_type="review_response",
                evidence_ids=_SYNTHETIC_EVIDENCE_IDS,
                allowed_action_ids={_SYNTHETIC_ACTION_ID},
                allowed_draft_types={"review_response"},
            )
            if (
                draft.draft_state != "ready"
                or not draft.approval_required
                or set(draft.evidence_used) != _SYNTHETIC_EVIDENCE_IDS
            ):
                raise ValueError("The made-up reply draft was not returned safely.")
    except GovernedAIProviderConnectionError as exc:
        result_status = "failed"
        reason_code = exc.reason_code[:120]
    except GovernedAIProviderError as exc:
        result_status = "failed"
        reason_code = exc.code[:120]
    except (TypeError, ValueError):
        result_status = "failed"
        reason_code = "ai_provider_review_response_qualification_invalid_output"
    except Exception:
        result_status = "failed"
        reason_code = "ai_provider_review_response_qualification_unexpected_error"
    latency_ms = min(60_000, max(0, int((perf_counter() - started) * 1_000)))
    artifact = {
        "connection_id": connection_id,
        "health_snapshot_id": health.id,
        "capability": CAPABILITY,
        "schema_version": CAPABILITY_SCHEMA_VERSION,
        "status": result_status,
        "reason_code": reason_code,
        "latency_ms": latency_ms,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "health_artifact_hash": health.artifact_hash,
        "connection_evidence_hash": connection.validation_evidence_hash,
        "customer_prompt_sent": False,
        "routing_enabled": False,
        "customer_review_sent": False,
        "review_status_changed": False,
        "may_post_response": False,
    }
    row = GovernedAIProviderCapabilityBenchmark(
        tenant_id=organization_id,
        organization_id=organization_id,
        connection_id=connection_id,
        health_snapshot_id=health.id,
        capability=CAPABILITY,
        schema_version=CAPABILITY_SCHEMA_VERSION,
        status=result_status,
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
        event_type="ai.provider_capability.review_response_qualification_created",
        payload={
            "connection_id": connection_id,
            "benchmark_id": row.id,
            "capability": CAPABILITY,
            "status": result_status,
            "reason_code": reason_code,
            "customer_prompt_sent": False,
            "routing_enabled": False,
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
        repeated = _benchmark_by_idempotency(
            db, organization_id=organization_id, idempotency_key=idempotency_key
        )
        assert repeated is not None
        return _benchmark_response(db, repeated, created=False, now=occurred_at)
    db.refresh(row)
    return _benchmark_response(db, row, created=True, now=occurred_at)


def _synthetic_context() -> dict[str, Any]:
    return {
        "contract": {
            "ai_role": "draft_one_review_response_only",
            "review_text_is_untrusted": True,
            "may_answer_other_questions": False,
            "may_execute_changes": False,
            "may_post_response": False,
            "synthetic": True,
        },
        "facts": {
            "review": {
                "evidence_id": "review:synthetic-review",
                "rating": 5,
                "comment": "The team arrived on time and explained the work clearly.",
                "response_status": "not_responded",
            },
            "business": {
                "evidence_id": "location:synthetic-location",
                "name": "Example Home Services",
                "city": "Example City",
                "region": "EX",
                "confirmed_services": ["Drain cleaning"],
            },
        },
        "allowed_evidence_ids": sorted(_SYNTHETIC_EVIDENCE_IDS),
        "allowed_actions": [
            {"action_id": _SYNTHETIC_ACTION_ID, "draft_types": ["review_response"]}
        ],
        "response_policy": {
            "version": "synthetic-review-response-v1",
            "rules": {
                "approval_required": True,
                "may_repeat_personal_information": False,
                "may_offer_compensation": False,
            },
        },
        "draft_request": {
            "action_id": _SYNTHETIC_ACTION_ID,
            "draft_type": "review_response",
            "approval_required": True,
            "body_max_characters": 600,
            "may_execute_changes": False,
            "may_post_response": False,
            "may_introduce_numeric_claims": False,
            "may_repeat_personal_information": False,
        },
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


def _benchmark_by_idempotency(
    db: Session,
    *,
    organization_id: str,
    idempotency_key: str,
) -> GovernedAIProviderCapabilityBenchmark | None:
    return (
        db.query(GovernedAIProviderCapabilityBenchmark)
        .filter(
            GovernedAIProviderCapabilityBenchmark.organization_id == organization_id,
            GovernedAIProviderCapabilityBenchmark.idempotency_key == idempotency_key,
        )
        .one_or_none()
    )


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
        "draft_only": True,
        "customer_review_sent": False,
        "review_status_changed": False,
        "may_post_response": False,
        "publishing_allowed": False,
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
        **list_review_response_qualification(
            db,
            organization_id=row.organization_id,
            connection_id=row.connection_id,
            now=now,
        ),
    }


def _require_qualification_schema(db: Session) -> None:
    if not _qualification_schema_available(db):
        raise _error(
            "Review reply private AI is not available yet.",
            "ai_provider_review_response_qualification_unavailable",
            409,
        )


def _qualification_schema_available(db: Session) -> bool:
    if not _capability_tables_available(db):
        return False
    try:
        constraints = inspect(db.get_bind()).get_check_constraints(
            GovernedAIProviderCapabilityBenchmark.__tablename__
        )
    except Exception:
        return False
    return any(CAPABILITY in str(item.get("sqltext") or "") for item in constraints)


def _unavailable_qualification() -> dict[str, Any]:
    state = "unavailable"
    return {
        "state": state,
        "capability": CAPABILITY,
        "customer_label": "Optional review reply wording",
        "latest_benchmark": None,
        "routing_enabled": False,
        "traffic_percentage": 0,
        "customer_prompts_allowed": False,
        "owner_activation_available": False,
        "automatic_activation_allowed": False,
        "automatic_changes_allowed": False,
        "draft_only": True,
        "customer_review_sent": False,
        "review_status_changed": False,
        "may_post_response": False,
        "publishing_allowed": False,
        "qualification_only": True,
        "truth": {
            "state": state,
            "summary": "Review reply private AI is not available yet.",
        },
    }


def _summary(state: str) -> str:
    if state == "eligible_for_later_review":
        return "The made-up review reply check passed. Customer reviews remain off."
    if state == "qualification_failed":
        return "The made-up review reply check did not pass; no customer review was sent."
    if state == "needs_attention":
        return "The saved check is no longer current. Refresh health evidence and run it again."
    return "Run the made-up review reply check before considering limited use."

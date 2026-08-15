from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
import json
import logging
import re
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.intelligence.contracts.governed_ai import GovernedEvidenceAnswer
from app.intelligence.lexicon import (
    SERVICE_BUSINESS_LANGUAGE_GUIDE_VERSION,
    get_active_lexicon,
    load_service_business_language_guide,
    service_business_language_guide_hash,
    simplify_internal_language,
)
from app.models.governed_ai import GovernedAIRun
from app.services import cost_economics_service, governed_ai_service, intelligence_service
from app.services.governed_ai_provider import (
    GovernedAIProviderError,
    GovernedAIQuestionProvider,
    MistralGovernedAIProvider,
)


FEATURE = "intelligence_question"
PROMPT_TEMPLATE_VERSION = "insightos-evidence-question-v1"
# The current governed-AI price card meters one bounded generation. The run's
# feature field keeps question usage distinguishable without creating an
# unpriced provider operation.
MISTRAL_OPERATION = governed_ai_service.MISTRAL_OPERATION
logger = logging.getLogger(__name__)
SENSITIVE_QUESTION_PATTERNS = (
    re.compile(
        r"\b(?:password|secret|api[_ -]?key|access[_ -]?token|bearer)\b\s*[:=]\s*\S+",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:sk|key)-[A-Za-z0-9_-]{16,}\b"),
)


def list_governed_answers(
    db: Session,
    *,
    organization_id: str,
    campaign_id: str,
    limit: int = 10,
) -> dict[str, Any]:
    campaign = governed_ai_service._campaign_for_organization(
        db,
        organization_id=organization_id,
        campaign_id=campaign_id,
    )
    rows = (
        db.query(GovernedAIRun)
        .filter(
            GovernedAIRun.organization_id == organization_id,
            GovernedAIRun.campaign_id == campaign.id,
            GovernedAIRun.feature == FEATURE,
            GovernedAIRun.status != "running",
        )
        .order_by(GovernedAIRun.created_at.desc())
        .limit(max(1, min(int(limit), 25)))
        .all()
    )
    return {
        "items": [_run_payload(row) for row in rows],
        "runtime": _runtime_status(),
        "allowance": governed_ai_service._action_allowance(
            db,
            organization_id=organization_id,
        ),
    }


def ask_governed_question(
    db: Session,
    *,
    organization_id: str,
    campaign_id: str,
    requested_by_user_id: str | None,
    question: str,
    retry_failed: bool = False,
    provider: GovernedAIQuestionProvider | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    occurred_at = governed_ai_service._as_utc(now or datetime.now(UTC))
    normalized_question = " ".join(question.strip().split())
    if len(normalized_question) < 3 or len(normalized_question) > 500:
        raise HTTPException(
            status_code=422,
            detail="Ask a question between 3 and 500 characters.",
        )
    if any(pattern.search(normalized_question) for pattern in SENSITIVE_QUESTION_PATTERNS):
        raise HTTPException(
            status_code=422,
            detail=(
                "Remove passwords, API keys, tokens, or other secrets before asking "
                "a question."
            ),
        )

    settings = get_settings()
    campaign = governed_ai_service._campaign_for_organization(
        db,
        organization_id=organization_id,
        campaign_id=campaign_id,
    )
    lexicon = get_active_lexicon(db, tenant_id=campaign.tenant_id)
    score = intelligence_service.get_latest_score(
        db,
        tenant_id=campaign.tenant_id,
        campaign_id=campaign.id,
    )
    recommendations = governed_ai_service._rank_active_recommendations(
        intelligence_service.get_recommendations(
            db,
            tenant_id=campaign.tenant_id,
            campaign_id=campaign.id,
        )
    )[:10]
    action_plans = intelligence_service.build_recommendation_action_plans(
        db,
        tenant_id=campaign.tenant_id,
        recommendations=recommendations,
    )
    work_items = intelligence_service.ensure_action_plan_occurrences(
        db,
        tenant_id=campaign.tenant_id,
        campaign_id=campaign.id,
        recommendations=recommendations,
        action_plans=action_plans,
        now=occurred_at,
    )
    context_bundle = governed_ai_service._build_context(
        campaign=campaign,
        score=score,
        recommendations=recommendations,
        lexicon=lexicon,
        action_plans=action_plans,
        work_items=work_items,
    )
    context = dict(context_bundle["context"])
    context["customer_question"] = normalized_question
    context["answer_rules"] = {
        "authority": "saved_location_evidence_only",
        "may_create_actions": False,
        "may_execute_changes": False,
        "unsupported_outcome_policy": "say_not_enough_information",
    }
    context_hash = governed_ai_service._hash_payload(context)
    prompt_hash = governed_ai_service._hash_payload(
        {
            "template_version": PROMPT_TEMPLATE_VERSION,
            "schema": GovernedEvidenceAnswer.model_json_schema(),
            "writing_guide_version": SERVICE_BUSINESS_LANGUAGE_GUIDE_VERSION,
            "writing_guide_hash": service_business_language_guide_hash(),
        }
    )
    backend = settings.ai_provider_backend.strip().lower()
    model_name = settings.mistral_model.strip() or "mistral-small-2603"
    provider_configured = provider is not None or (
        backend == "mistral" and bool(settings.mistral_api_key.strip())
    )
    idempotency_base = governed_ai_service._hash_payload(
        {
            "organization_id": organization_id,
            "campaign_id": campaign.id,
            "feature": FEATURE,
            "context_hash": context_hash,
            "prompt_hash": prompt_hash,
            "model_name": model_name,
            "provider_configured": provider_configured,
            "period": occurred_at.strftime("%Y-%m"),
        }
    )
    idempotency_key = f"ai:{FEATURE}:{idempotency_base}"
    existing = governed_ai_service._run_by_key(
        db,
        organization_id=organization_id,
        idempotency_key=idempotency_key,
    )
    if existing is not None:
        if existing.status == "running":
            raise governed_ai_service._already_running_error()
        if existing.status == "validated":
            return _response(db, existing, idempotent_replay=True)
        if not retry_failed:
            recovered = governed_ai_service._validated_retry_for_key(
                db,
                organization_id=organization_id,
                idempotency_key=idempotency_key,
            )
            return _response(db, recovered or existing, idempotent_replay=True)
        retry_bucket = occurred_at.replace(
            minute=(occurred_at.minute // 15) * 15,
            second=0,
            microsecond=0,
        )
        idempotency_key = f"{idempotency_key}:retry:{retry_bucket.isoformat()}"
        retry_existing = governed_ai_service._run_by_key(
            db,
            organization_id=organization_id,
            idempotency_key=idempotency_key,
        )
        if retry_existing is not None:
            return _response(db, retry_existing, idempotent_replay=True)

    fallback = _fallback_answer(normalized_question)
    plan = cost_economics_service.resolve_plan_economics(
        governed_ai_service._organization_plan_type(db, organization_id)
    )
    action_limit = governed_ai_service.MONTHLY_ACTION_LIMITS[plan.code]
    actions_used = governed_ai_service._provider_actions_used(
        db,
        organization_id=organization_id,
        now=occurred_at,
    )
    if actions_used >= action_limit:
        row = _new_run(
            campaign=campaign,
            organization_id=organization_id,
            requested_by_user_id=requested_by_user_id,
            provider_name=backend or "deterministic",
            model_name=model_name,
            lexicon=lexicon,
            context_hash=context_hash,
            prompt_hash=prompt_hash,
            idempotency_key=idempotency_key,
            allowed_action_ids=context_bundle["allowed_action_ids"],
            evidence_ids=context_bundle["evidence_ids"],
            now=occurred_at,
        )
        db.add(row)
        concurrent = governed_ai_service._commit_new_run(db, row)
        if concurrent is not None:
            return _response(db, concurrent, idempotent_replay=True)
        _finalize_fallback(
            db,
            row,
            output=fallback,
            provider_state="allowance_exhausted",
            error_code="ai_action_allowance_exhausted",
            rejection_reason=(
                f"The plan's {action_limit}-action monthly AI allowance is exhausted."
            ),
            now=occurred_at,
        )
        return _response(db, row, idempotent_replay=False)

    concurrency_limit = governed_ai_service.CONCURRENCY_LIMITS[plan.code]
    running = (
        db.query(func.count(GovernedAIRun.id))
        .filter(
            GovernedAIRun.organization_id == organization_id,
            GovernedAIRun.status == "running",
            GovernedAIRun.created_at >= occurred_at - timedelta(minutes=5),
        )
        .scalar()
        or 0
    )
    if running >= concurrency_limit:
        raise governed_ai_service._already_running_error()

    row = _new_run(
        campaign=campaign,
        organization_id=organization_id,
        requested_by_user_id=requested_by_user_id,
        provider_name=provider.name if provider is not None else (backend or "deterministic"),
        model_name=provider.model_name if provider is not None else model_name,
        lexicon=lexicon,
        context_hash=context_hash,
        prompt_hash=prompt_hash,
        idempotency_key=idempotency_key,
        allowed_action_ids=context_bundle["allowed_action_ids"],
        evidence_ids=context_bundle["evidence_ids"],
        now=occurred_at,
    )
    db.add(row)
    concurrent = governed_ai_service._commit_new_run(db, row)
    if concurrent is not None:
        if concurrent.status == "running":
            raise governed_ai_service._already_running_error()
        return _response(db, concurrent, idempotent_replay=True)
    db.refresh(row)

    context_json = json.dumps(context, sort_keys=True, separators=(",", ":"))
    language_guide = load_service_business_language_guide()
    estimated_input_tokens = max(
        1,
        (len(context_json) + len(language_guide) + 3) // 4 + 260,
    )
    if estimated_input_tokens > settings.ai_max_input_tokens:
        _finalize_fallback(
            db,
            row,
            output=fallback,
            provider_state="context_rejected",
            error_code="ai_context_too_large",
            rejection_reason="The verified context exceeded the configured token ceiling.",
            now=occurred_at,
        )
        return _response(db, row, idempotent_replay=False)

    if not provider_configured:
        _finalize_fallback(
            db,
            row,
            output=fallback,
            provider_state="not_configured",
            error_code="ai_provider_not_configured",
            rejection_reason="Mistral has not been connected to the server.",
            now=occurred_at,
        )
        return _response(db, row, idempotent_replay=False)

    if provider is None:
        if backend != "mistral":
            _finalize_fallback(
                db,
                row,
                output=fallback,
                provider_state="not_configured",
                error_code="ai_provider_backend_unsupported",
                rejection_reason=f"Unsupported AI provider backend: {backend or 'empty'}.",
                now=occurred_at,
            )
            return _response(db, row, idempotent_replay=False)
        provider = MistralGovernedAIProvider(
            api_key=settings.mistral_api_key,
            endpoint=settings.mistral_api_endpoint,
            model_name=model_name,
            timeout_seconds=settings.ai_provider_timeout_seconds,
            max_output_tokens=settings.ai_max_output_tokens,
            max_attempts=settings.ai_provider_max_attempts,
        )

    reservation = None
    try:
        reservation = cost_economics_service.reserve_provider_cost(
            db,
            organization_id=organization_id,
            business_location_id=campaign.business_location_id,
            campaign_id=campaign.id,
            provider_name=provider.name,
            capability=governed_ai_service.MISTRAL_CAPABILITY,
            operation=MISTRAL_OPERATION,
            credential_owner="platform",
            quantity=1,
            idempotency_key=idempotency_key,
            model_name=provider.model_name,
            input_tokens=estimated_input_tokens,
            output_tokens=settings.ai_max_output_tokens,
            now=occurred_at,
        )
    except cost_economics_service.CostEconomicsError as exc:
        _finalize_fallback(
            db,
            row,
            output=fallback,
            provider_state=(
                "allowance_exhausted"
                if isinstance(exc, cost_economics_service.CostAllowanceExceeded)
                else "cost_control_blocked"
            ),
            error_code=exc.reason_code,
            rejection_reason=str(exc),
            now=occurred_at,
        )
        return _response(db, row, idempotent_replay=False)

    row.cost_reservation_id = reservation.id
    row.price_card_version = reservation.price_card_version
    row.estimated_cost = reservation.estimated_cost
    db.commit()

    try:
        cost_economics_service.authorize_reserved_provider_dispatch(
            db,
            reservation=reservation,
        )
    except cost_economics_service.CostEconomicsError as exc:
        _finalize_fallback(
            db,
            row,
            output=fallback,
            provider_state="cost_control_blocked",
            error_code=exc.reason_code,
            rejection_reason=str(exc),
            now=occurred_at,
        )
        return _response(db, row, idempotent_replay=False)

    try:
        provider_response = provider.answer_question(
            context=context,
            output_schema=GovernedEvidenceAnswer.model_json_schema(),
            prompt_template_version=PROMPT_TEMPLATE_VERSION,
        )
    except GovernedAIProviderError as exc:
        if exc.provider_may_have_processed:
            terminal = cost_economics_service.reconcile_provider_cost(
                db,
                reservation=reservation,
                provider_reported_cost=reservation.estimated_cost,
                now=occurred_at,
            )
            row.reconciled_cost = terminal.provider_reported_cost or reservation.estimated_cost
        else:
            cost_economics_service.release_provider_cost(
                db,
                reservation=reservation,
                now=occurred_at,
            )
        _finalize_fallback(
            db,
            row,
            output=fallback,
            provider_state="unavailable",
            error_code=exc.code,
            rejection_reason=str(exc),
            now=occurred_at,
        )
        return _response(db, row, idempotent_replay=False)
    except Exception:
        logger.exception(
            "Unexpected governed AI question failure",
            extra={
                "organization_id": organization_id,
                "campaign_id": campaign.id,
                "provider_name": provider.name,
            },
        )
        terminal = cost_economics_service.reconcile_provider_cost(
            db,
            reservation=reservation,
            provider_reported_cost=reservation.estimated_cost,
            now=occurred_at,
        )
        row.reconciled_cost = terminal.provider_reported_cost or reservation.estimated_cost
        _finalize_fallback(
            db,
            row,
            output=fallback,
            provider_state="unavailable",
            error_code="ai_provider_unexpected_error",
            rejection_reason="The AI provider could not complete the answer.",
            now=occurred_at,
        )
        return _response(db, row, idempotent_replay=False)

    actual_input = provider_response.input_tokens or estimated_input_tokens
    actual_output = provider_response.output_tokens or settings.ai_max_output_tokens
    try:
        actual_cost = cost_economics_service.calculate_provider_cost(
            db,
            provider_name=provider.name,
            capability=governed_ai_service.MISTRAL_CAPABILITY,
            operation=MISTRAL_OPERATION,
            quantity=1,
            model_name=provider.model_name,
            input_tokens=actual_input,
            output_tokens=actual_output,
            now=occurred_at,
        )
    except cost_economics_service.CostEconomicsError as exc:
        terminal = cost_economics_service.reconcile_provider_cost(
            db,
            reservation=reservation,
            provider_reported_cost=reservation.estimated_cost,
            now=occurred_at,
        )
        row.input_tokens = actual_input
        row.output_tokens = actual_output
        row.reconciled_cost = terminal.provider_reported_cost or reservation.estimated_cost
        row.provider_request_id = provider_response.provider_request_id
        _finalize_fallback(
            db,
            row,
            output=fallback,
            provider_state="cost_control_blocked",
            error_code=exc.reason_code,
            rejection_reason="The provider response could not be safely priced.",
            now=occurred_at,
        )
        return _response(db, row, idempotent_replay=False)

    terminal = cost_economics_service.reconcile_provider_cost(
        db,
        reservation=reservation,
        provider_reported_cost=actual_cost,
        now=occurred_at,
    )
    row.input_tokens = actual_input
    row.output_tokens = actual_output
    row.reconciled_cost = terminal.provider_reported_cost or actual_cost
    row.provider_request_id = provider_response.provider_request_id
    row.response_hash = governed_ai_service._hash_payload(provider_response.payload)
    try:
        output = GovernedEvidenceAnswer.model_validate(provider_response.payload)
        output.validate_against_context(
            original_question=normalized_question,
            evidence_ids=set(context_bundle["evidence_ids"]),
            allowed_action_ids=set(context_bundle["allowed_action_ids"]),
        )
    except (TypeError, ValueError) as exc:
        row.status = "rejected"
        row.provider_state = "invalid_output"
        row.output_payload = _output_payload(fallback, context=context)
        row.error_code = "ai_output_validation_failed"
        row.rejection_reason = str(exc)[:2000]
        row.completed_at = occurred_at
        db.commit()
        db.refresh(row)
        return _response(db, row, idempotent_replay=False)

    row.status = "validated"
    row.provider_state = "ready"
    row.output_payload = _output_payload(output, context=context)
    row.selected_action_id = (
        output.related_action_ids[0] if output.related_action_ids else None
    )
    row.completed_at = occurred_at
    db.commit()
    db.refresh(row)
    return _response(db, row, idempotent_replay=False)


def _fallback_answer(question: str) -> GovernedEvidenceAnswer:
    return GovernedEvidenceAnswer(
        question=question,
        answer=(
            "I could not prepare a verified answer right now. Your saved facts, "
            "action plan, and checklist are still available on this page."
        ),
        answer_state="temporarily_unavailable",
        evidence_used=[],
        related_action_ids=[],
        uncertainties=[
            "No new answer was added because the plain-language service was unavailable."
        ],
    )


def _new_run(
    *,
    campaign: Any,
    organization_id: str,
    requested_by_user_id: str | None,
    provider_name: str,
    model_name: str,
    lexicon: Any,
    context_hash: str,
    prompt_hash: str,
    idempotency_key: str,
    allowed_action_ids: list[str],
    evidence_ids: list[str],
    now: datetime,
) -> GovernedAIRun:
    return GovernedAIRun(
        tenant_id=campaign.tenant_id,
        organization_id=organization_id,
        campaign_id=campaign.id,
        business_location_id=campaign.business_location_id,
        requested_by_user_id=requested_by_user_id,
        feature=FEATURE,
        provider_name=provider_name,
        model_name=model_name,
        prompt_template_version=PROMPT_TEMPLATE_VERSION,
        lexicon_id=lexicon.meta.lexicon_id,
        lexicon_version=lexicon.meta.version,
        context_hash=context_hash,
        prompt_hash=prompt_hash,
        idempotency_key=idempotency_key,
        status="running",
        provider_state="pending",
        allowed_action_ids=allowed_action_ids,
        evidence_refs=evidence_ids,
        output_payload={},
        input_tokens=0,
        output_tokens=0,
        estimated_cost=Decimal("0"),
        reconciled_cost=Decimal("0"),
        created_at=now,
    )


def _finalize_fallback(
    db: Session,
    row: GovernedAIRun,
    *,
    output: GovernedEvidenceAnswer,
    provider_state: str,
    error_code: str,
    rejection_reason: str,
    now: datetime,
) -> None:
    row.status = "fallback"
    row.provider_state = provider_state
    row.output_payload = output.model_dump(mode="json")
    row.error_code = error_code
    row.rejection_reason = rejection_reason[:2000]
    row.completed_at = now
    db.commit()
    db.refresh(row)


def _output_payload(
    output: GovernedEvidenceAnswer,
    *,
    context: dict[str, Any],
) -> dict[str, Any]:
    payload = output.model_dump(mode="json")
    payload["evidence_details"] = _evidence_details(
        context,
        evidence_used=output.evidence_used,
    )
    payload["related_actions"] = _related_actions(
        context,
        action_ids=output.related_action_ids,
    )
    return payload


def _evidence_details(
    context: dict[str, Any],
    *,
    evidence_used: list[str],
) -> list[dict[str, Any]]:
    facts = context.get("facts") if isinstance(context.get("facts"), dict) else {}
    candidates: dict[str, dict[str, Any]] = {}
    campaign = facts.get("campaign") if isinstance(facts.get("campaign"), dict) else {}
    if campaign.get("evidence_id"):
        candidates[str(campaign["evidence_id"])] = {
            "evidence_id": str(campaign["evidence_id"]),
            "label": "Saved business details",
            "detail": str(campaign.get("domain") or campaign.get("name") or "This location"),
            "captured_at": None,
        }
    score = facts.get("latest_score") if isinstance(facts.get("latest_score"), dict) else {}
    if score.get("evidence_id"):
        candidates[str(score["evidence_id"])] = {
            "evidence_id": str(score["evidence_id"]),
            "label": "Latest saved opportunity score",
            "detail": str(score.get("score_value")),
            "captured_at": score.get("captured_at"),
        }
    recommendations = facts.get("recommendations") or []
    for recommendation in recommendations:
        if not isinstance(recommendation, dict) or not recommendation.get("evidence_id"):
            continue
        plan = recommendation.get("action_plan") or {}
        label = str(plan.get("display_name") or "Saved recommendation")
        detail = simplify_internal_language(
            str(recommendation.get("rationale") or "Saved location evidence"),
            max_words=28,
            max_sentences=2,
            action_first=False,
        ) or "Saved location evidence"
        candidates[str(recommendation["evidence_id"])] = {
            "evidence_id": str(recommendation["evidence_id"]),
            "label": label,
            "detail": detail,
            "captured_at": recommendation.get("created_at"),
        }
    return [candidates[item] for item in evidence_used if item in candidates]


def _related_actions(
    context: dict[str, Any],
    *,
    action_ids: list[str],
) -> list[dict[str, Any]]:
    allowed = {
        str(item.get("action_id")): item
        for item in (context.get("allowed_actions") or [])
        if isinstance(item, dict) and item.get("action_id")
    }
    return [
        {
            "action_id": action_id,
            "display_name": allowed[action_id].get("display_name"),
            "why_it_matters": allowed[action_id].get("why_it_matters"),
        }
        for action_id in action_ids
        if action_id in allowed
    ]


def _run_payload(row: GovernedAIRun) -> dict[str, Any]:
    output = dict(row.output_payload or {})
    return {
        "id": row.id,
        "campaign_id": row.campaign_id,
        "feature": row.feature,
        "status": row.status,
        "provider_state": row.provider_state,
        "provider_name": row.provider_name,
        "model_name": row.model_name,
        "prompt_template_version": row.prompt_template_version,
        "lexicon_version": row.lexicon_version,
        "output": output,
        "usage": {
            "input_tokens": row.input_tokens,
            "output_tokens": row.output_tokens,
            "estimated_cost": float(row.estimated_cost or 0),
            "reconciled_cost": float(row.reconciled_cost or 0),
            "currency": "USD",
        },
        "evidence_count": len(output.get("evidence_used") or []),
        "error_code": row.error_code,
        "rejection_reason": row.rejection_reason,
        "created_at": row.created_at.isoformat(),
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
        "truth": {
            "classification": "generated" if row.status == "validated" else "heuristic",
            "states": (
                ["generated", "evidence_bounded"]
                if row.status == "validated"
                else ["heuristic", "evidence_bounded"]
            ),
            "provider_state": row.provider_state,
            "operator_state": "recommendation_only",
            "summary": (
                "AI explained the selected location's saved evidence without changing actions or business data."
                if row.status == "validated"
                else "No new AI answer was accepted; the saved facts and actions remain unchanged."
            ),
            "reasons": [
                "saved_evidence_is_the_only_answer_source",
                "deterministic_engine_retains_decision_authority",
                "no_automatic_site_changes",
            ],
        },
    }


def _response(
    db: Session,
    row: GovernedAIRun,
    *,
    idempotent_replay: bool,
) -> dict[str, Any]:
    return {
        "item": _run_payload(row),
        "runtime": _runtime_status(),
        "allowance": governed_ai_service._action_allowance(
            db,
            organization_id=row.organization_id,
        ),
        "idempotent_replay": idempotent_replay,
    }


def _runtime_status() -> dict[str, Any]:
    settings = get_settings()
    backend = settings.ai_provider_backend.strip().lower()
    return {
        "backend": backend or "disabled",
        "model": settings.mistral_model,
        "configured": backend == "mistral" and bool(settings.mistral_api_key.strip()),
        "decision_authority": "deterministic_engine",
        "ai_role": "answer_questions_from_saved_location_evidence",
        "automatic_execution": False,
    }

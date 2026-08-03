from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
import hashlib
import json
import logging
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.intelligence.contracts.governed_ai import GovernedIntelligenceBrief
from app.intelligence.lexicon import (
    SERVICE_BUSINESS_LANGUAGE_GUIDE_VERSION,
    SUMMARY_MAX_WORDS,
    WHY_NOW_MAX_WORDS,
    build_ai_decision_context,
    get_active_lexicon,
    load_service_business_language_guide,
    service_business_language_guide_hash,
    simplify_internal_language,
)
from app.models.campaign import Campaign
from app.models.governed_ai import GovernedAIRun
from app.models.intelligence import StrategyRecommendation
from app.services import cost_economics_service, intelligence_service
from app.services.governed_ai_provider import (
    GovernedAIProvider,
    GovernedAIProviderError,
    MistralGovernedAIProvider,
)


FEATURE = "intelligence_brief"
PROMPT_TEMPLATE_VERSION = "insightos-daily-action-brief-v1"
MISTRAL_CAPABILITY = "governed_ai"
MISTRAL_OPERATION = "intelligence_brief"
DAILY_ACTION_LIMIT = 3
MONTHLY_ACTION_LIMITS = {
    "solo": 31,
    "multi_location": 310,
    "enterprise": 1000,
}
CONCURRENCY_LIMITS = {
    "solo": 1,
    "multi_location": 2,
    "enterprise": 4,
}
logger = logging.getLogger(__name__)


def latest_governed_brief(
    db: Session,
    *,
    organization_id: str,
    campaign_id: str,
) -> dict[str, Any]:
    campaign = _campaign_for_organization(
        db,
        organization_id=organization_id,
        campaign_id=campaign_id,
    )
    row = (
        db.query(GovernedAIRun)
        .filter(
            GovernedAIRun.organization_id == organization_id,
            GovernedAIRun.campaign_id == campaign.id,
            GovernedAIRun.feature == FEATURE,
            GovernedAIRun.status != "running",
        )
        .order_by(GovernedAIRun.created_at.desc())
        .first()
    )
    return {
        "item": _run_payload(db, row) if row is not None else None,
        "runtime": _runtime_status(),
        "allowance": _action_allowance(db, organization_id=organization_id),
    }


def generate_governed_brief(
    db: Session,
    *,
    organization_id: str,
    campaign_id: str,
    requested_by_user_id: str | None,
    retry_failed: bool = False,
    provider: GovernedAIProvider | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    occurred_at = _as_utc(now or datetime.now(UTC))
    settings = get_settings()
    campaign = _campaign_for_organization(
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
    recommendations = intelligence_service.get_recommendations(
        db,
        tenant_id=campaign.tenant_id,
        campaign_id=campaign.id,
    )
    recommendations = _rank_active_recommendations(recommendations)[:10]
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
    context_bundle = _build_context(
        campaign=campaign,
        score=score,
        recommendations=recommendations,
        lexicon=lexicon,
        action_plans=action_plans,
        work_items=work_items,
    )
    context = context_bundle["context"]
    context_hash = _hash_payload(context)
    prompt_hash = _hash_payload(
        {
            "template_version": PROMPT_TEMPLATE_VERSION,
            "schema": GovernedIntelligenceBrief.model_json_schema(),
            "writing_guide_version": SERVICE_BUSINESS_LANGUAGE_GUIDE_VERSION,
            "writing_guide_hash": service_business_language_guide_hash(),
        }
    )
    backend = settings.ai_provider_backend.strip().lower()
    model_name = settings.mistral_model.strip() or "mistral-small-2603"
    provider_configured = provider is not None or (
        backend == "mistral" and bool(settings.mistral_api_key.strip())
    )
    idempotency_base = _hash_payload(
        {
            "organization_id": organization_id,
            "campaign_id": campaign.id,
            "feature": FEATURE,
            "context_hash": context_hash,
            "prompt_hash": prompt_hash,
            "model_name": model_name,
            "provider_configured": provider_configured,
            "period": occurred_at.strftime("%Y-%m"),
            "day": occurred_at.strftime("%Y-%m-%d"),
        }
    )
    idempotency_key = f"ai:{FEATURE}:{idempotency_base}"
    existing = _run_by_key(
        db,
        organization_id=organization_id,
        idempotency_key=idempotency_key,
    )
    if existing is not None:
        if existing.status == "running":
            raise _already_running_error()
        if existing.status == "validated":
            return {
                "item": _run_payload(db, existing),
                "runtime": _runtime_status(),
                "allowance": _action_allowance(db, organization_id=organization_id),
                "idempotent_replay": True,
            }
        if not retry_failed:
            recovered = _validated_retry_for_key(
                db,
                organization_id=organization_id,
                idempotency_key=idempotency_key,
            )
            return {
                "item": _run_payload(db, recovered or existing),
                "runtime": _runtime_status(),
                "allowance": _action_allowance(db, organization_id=organization_id),
                "idempotent_replay": True,
            }
        retry_bucket = occurred_at.replace(
            minute=(occurred_at.minute // 15) * 15,
            second=0,
            microsecond=0,
        )
        idempotency_key = (
            f"{idempotency_key}:retry:{retry_bucket.isoformat()}"
        )
        retry_existing = _run_by_key(
            db,
            organization_id=organization_id,
            idempotency_key=idempotency_key,
        )
        if retry_existing is not None:
            return {
                "item": _run_payload(db, retry_existing),
                "runtime": _runtime_status(),
                "allowance": _action_allowance(db, organization_id=organization_id),
                "idempotent_replay": True,
            }

    plan = cost_economics_service.resolve_plan_economics(
        _organization_plan_type(db, organization_id)
    )
    action_limit = MONTHLY_ACTION_LIMITS[plan.code]
    actions_used = _provider_actions_used(
        db,
        organization_id=organization_id,
        now=occurred_at,
    )
    fallback = _fallback_output(
        recommendations=recommendations,
        evidence_ids=context_bundle["evidence_ids"],
        deterministic_action=context_bundle["deterministic_action"],
        daily_action_ids=context_bundle["daily_action_ids"],
        uncertainty=(
            "The daily explanation is unavailable. Your saved recommendation "
            "is still available."
        ),
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
        concurrent = _commit_new_run(db, row)
        if concurrent is not None:
            if concurrent.status == "running":
                raise _already_running_error()
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

    concurrency_limit = CONCURRENCY_LIMITS[plan.code]
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
        raise HTTPException(
            status_code=409,
            detail={
                "message": "An AI explanation is already being prepared for this account.",
                "reason_code": "ai_concurrency_limit",
            },
        )

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
    concurrent = _commit_new_run(db, row)
    if concurrent is not None:
        if concurrent.status == "running":
            raise _already_running_error()
        return _response(db, concurrent, idempotent_replay=True)
    db.refresh(row)

    context_json = json.dumps(context, sort_keys=True, separators=(",", ":"))
    language_guide = load_service_business_language_guide()
    estimated_input_tokens = max(
        1,
        (len(context_json) + len(language_guide) + 3) // 4 + 220,
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
            capability=MISTRAL_CAPABILITY,
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
        provider_response = provider.generate(
            context=context,
            output_schema=GovernedIntelligenceBrief.model_json_schema(),
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
            "Unexpected governed AI provider failure",
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
        row.reconciled_cost = (
            terminal.provider_reported_cost or reservation.estimated_cost
        )
        _finalize_fallback(
            db,
            row,
            output=fallback,
            provider_state="unavailable",
            error_code="ai_provider_unexpected_error",
            rejection_reason="The AI provider could not complete the explanation.",
            now=occurred_at,
        )
        return _response(db, row, idempotent_replay=False)

    actual_input = provider_response.input_tokens or estimated_input_tokens
    actual_output = provider_response.output_tokens or settings.ai_max_output_tokens
    try:
        actual_cost = cost_economics_service.calculate_provider_cost(
            db,
            provider_name=provider.name,
            capability=MISTRAL_CAPABILITY,
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
        row.reconciled_cost = (
            terminal.provider_reported_cost or reservation.estimated_cost
        )
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
    row.response_hash = _hash_payload(provider_response.payload)
    try:
        output = GovernedIntelligenceBrief.model_validate(provider_response.payload)
        deterministic_action = context_bundle["deterministic_action"]
        output.validate_against_context(
            evidence_ids=set(context_bundle["evidence_ids"]),
            deterministic_action_id=(
                deterministic_action.get("action_id")
                if deterministic_action is not None
                else None
            ),
            deterministic_daily_action_ids=context_bundle["daily_action_ids"],
            action_requires_approval=bool(
                deterministic_action
                and int(deterministic_action.get("risk_tier") or 0) >= 2
            ),
        )
    except (TypeError, ValueError) as exc:
        row.status = "rejected"
        row.provider_state = "invalid_output"
        row.output_payload = fallback.model_dump(mode="json")
        row.selected_action_id = fallback.selected_action_id
        row.error_code = "ai_output_validation_failed"
        row.rejection_reason = str(exc)[:2000]
        row.completed_at = occurred_at
        logger.warning(
            "Governed AI output failed deterministic validation",
            extra={
                "organization_id": row.organization_id,
                "campaign_id": row.campaign_id,
                "provider_name": row.provider_name,
                "model_name": row.model_name,
                "provider_state": row.provider_state,
                "error_code": row.error_code,
                "run_id": row.id,
            },
        )
        db.commit()
        db.refresh(row)
        return _response(db, row, idempotent_replay=False)

    row.status = "validated"
    row.provider_state = "ready"
    row.output_payload = output.model_dump(mode="json")
    row.selected_action_id = output.selected_action_id
    row.completed_at = occurred_at
    db.commit()
    db.refresh(row)
    return _response(db, row, idempotent_replay=False)


def _build_context(
    *,
    campaign: Campaign,
    score: Any,
    recommendations: list[StrategyRecommendation],
    lexicon: Any,
    action_plans: dict[str, dict[str, Any]],
    work_items: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    evidence_ids = [
        f"campaign:{campaign.id}",
        f"intelligence_score:{score.id}",
    ]
    facts = {
        "campaign": {
            "evidence_id": evidence_ids[0],
            "name": campaign.name[:255],
            "domain": campaign.domain[:320],
            "setup_state": campaign.setup_state,
        },
        "latest_score": {
            "evidence_id": evidence_ids[1],
            "score_value": score.score_value,
            "score_type": score.score_type,
            "captured_at": score.captured_at.isoformat(),
        },
        "recommendations": [],
    }
    assessments: list[dict[str, Any]] = []
    action_ids: list[str] = []
    current_work_action_ids: list[str] = []
    diagnostic_ids: list[str] = []
    for recommendation in recommendations:
        plan = action_plans.get(recommendation.id)
        work_item = work_items.get(recommendation.id)
        evidence_id = f"recommendation:{recommendation.id}"
        evidence_ids.append(evidence_id)
        facts["recommendations"].append(
            {
                "evidence_id": evidence_id,
                "recommendation_type": recommendation.recommendation_type,
                "rationale": recommendation.rationale[:1200],
                "confidence": recommendation.confidence_score,
                "risk_tier": recommendation.risk_tier,
                "status": str(recommendation.status),
                "created_at": recommendation.created_at.isoformat(),
                "action_plan": (
                    {
                        "action_id": plan.get("action_id"),
                        "display_name": plan.get("display_name"),
                        "why_it_matters": plan.get("why_it_matters"),
                        "effort": plan.get("effort"),
                        "owner_role": plan.get("owner_role"),
                    }
                    if plan is not None
                    else None
                ),
                "current_work": _bounded_work_context(work_item),
            }
        )
        assessments.append(
            {
                "assessment_id": evidence_id,
                "status": str(recommendation.status),
                "recommendation_type": recommendation.recommendation_type,
                "confidence": recommendation.confidence_score,
                "risk_tier": recommendation.risk_tier,
            }
        )
        candidate_ids, candidate_diagnostics = _candidate_ids(
            recommendation,
            lexicon=lexicon,
        )
        for action_id in candidate_ids:
            if action_id not in action_ids:
                action_ids.append(action_id)
        for diagnostic_id in candidate_diagnostics:
            if diagnostic_id not in diagnostic_ids:
                diagnostic_ids.append(diagnostic_id)
        plan_action_id = str(plan.get("action_id")) if plan is not None else ""
        if (
            plan_action_id
            and work_item is not None
            and work_item.get("status") in {"ready", "in_progress", "blocked"}
            and work_item.get("next_step") is not None
            and plan_action_id not in current_work_action_ids
        ):
            current_work_action_ids.append(plan_action_id)

    context = build_ai_decision_context(
        lexicon,
        facts=facts,
        deterministic_assessments=assessments,
        diagnostic_ids=diagnostic_ids,
        action_ids=action_ids,
    )
    allowed_by_id = {
        item["action_id"]: item
        for item in context["allowed_actions"]
        if isinstance(item, dict) and item.get("action_id")
    }
    ordered_actions = [
        allowed_by_id[action_id]
        for action_id in current_work_action_ids
        if action_id in allowed_by_id
    ]
    deterministic_action = ordered_actions[0] if ordered_actions else None
    daily_action_ids = [
        str(item["action_id"])
        for item in ordered_actions[:DAILY_ACTION_LIMIT]
    ]
    context["allowed_actions"] = ordered_actions
    context["deterministic_selection"] = {
        "selected_action_id": (
            deterministic_action.get("action_id")
            if deterministic_action is not None
            else None
        ),
        "approval_required": bool(
            deterministic_action
            and int(deterministic_action.get("risk_tier") or 0) >= 2
        ),
        "daily_action_ids": daily_action_ids,
        "daily_action_limit": DAILY_ACTION_LIMIT,
        "authority": "deterministic_engine",
    }
    context["customer_language_standard"] = {
        "name": "InsightOS Service-Business Plain-Language Guide",
        "version": SERVICE_BUSINESS_LANGUAGE_GUIDE_VERSION,
        "summary_max_words": SUMMARY_MAX_WORDS,
        "why_now_max_words": WHY_NOW_MAX_WORDS,
        "required_order": "action_first_then_observable_problem",
        "audience": "busy_local_service_business_owner",
    }
    context["allowed_evidence_ids"] = evidence_ids
    return {
        "context": context,
        "evidence_ids": evidence_ids,
        "allowed_action_ids": [
            str(item["action_id"]) for item in ordered_actions
        ],
        "daily_action_ids": daily_action_ids,
        "deterministic_action": deterministic_action,
    }


def _rank_active_recommendations(
    recommendations: list[StrategyRecommendation],
) -> list[StrategyRecommendation]:
    active = [
        item
        for item in recommendations
        if str(getattr(item.status, "value", item.status)) != "ARCHIVED"
        and item.recommendation_type != "strategy_bundle_record"
    ]
    return sorted(
        active,
        key=lambda item: (
            int(item.risk_tier or 0),
            float(item.confidence_score or item.confidence or 0),
            _as_utc(item.created_at),
        ),
        reverse=True,
    )


def _bounded_work_context(work_item: dict[str, Any] | None) -> dict[str, Any] | None:
    if work_item is None:
        return None
    progress = work_item.get("progress") or {}
    next_step = work_item.get("next_step") or {}
    return {
        "cadence": work_item.get("cadence"),
        "due_state": work_item.get("due_state"),
        "status": work_item.get("status"),
        "completed_steps": int(progress.get("completed_required") or 0),
        "total_steps": int(progress.get("required_total") or 0),
        "next_step": next_step.get("instruction"),
        "next_step_status": next_step.get("status"),
    }


def _candidate_ids(
    recommendation: StrategyRecommendation,
    *,
    lexicon: Any,
) -> tuple[list[str], list[str]]:
    action_ids: list[str] = []
    diagnostic_ids: list[str] = []
    recommendation_type = str(recommendation.recommendation_type or "")
    candidates = [recommendation_type]
    if "::" in recommendation_type:
        candidates.append(recommendation_type.rsplit("::", 1)[-1])
    try:
        evidence = json.loads(recommendation.evidence_json or "{}")
    except json.JSONDecodeError:
        evidence = {}
    if isinstance(evidence, dict):
        for key in ("action_id", "recommended_action_id"):
            if evidence.get(key):
                candidates.append(str(evidence[key]))
        raw_actions = evidence.get("recommended_actions")
        if isinstance(raw_actions, list):
            candidates.extend(str(item) for item in raw_actions)
        raw_diagnostics = evidence.get("diagnostic_ids")
        if isinstance(raw_diagnostics, list):
            diagnostic_ids.extend(
                str(item)
                for item in raw_diagnostics
                if str(item) in lexicon.diagnostic_index
            )
    for candidate in candidates:
        if candidate in lexicon.action_index and candidate not in action_ids:
            action = lexicon.action_index[candidate]
            if action.ai_allowed:
                action_ids.append(candidate)
    return action_ids, diagnostic_ids


def _fallback_output(
    *,
    recommendations: list[StrategyRecommendation],
    evidence_ids: list[str],
    deterministic_action: dict[str, Any] | None,
    daily_action_ids: list[str],
    uncertainty: str,
) -> GovernedIntelligenceBrief:
    first = recommendations[0] if recommendations else None
    if first is not None:
        summary = simplify_internal_language(
            first.rationale,
            max_words=SUMMARY_MAX_WORDS,
        ) or "Review the first saved recommendation for this location."
        evidence_used = [f"recommendation:{first.id}"]
    else:
        summary = "Check this location again later. There is no specific next step yet."
        evidence_used = [evidence_ids[0]]
    if deterministic_action is not None:
        why_now = simplify_internal_language(
            str(deterministic_action.get("why_it_matters") or summary),
            max_words=WHY_NOW_MAX_WORDS,
            max_sentences=1,
            action_first=False,
        ) or "This is the safest useful action supported by the information available now."
        action_id = str(deterministic_action["action_id"])
        approval_required = int(deterministic_action.get("risk_tier") or 0) >= 2
    else:
        why_now = (
            "Review the saved information before choosing work because there is "
            "not enough information to suggest a safe action yet."
        )
        action_id = None
        approval_required = False
    return GovernedIntelligenceBrief(
        summary=summary,
        why_now=why_now,
        selected_action_id=action_id,
        daily_action_ids=daily_action_ids,
        evidence_used=evidence_used,
        uncertainties=[uncertainty],
        approval_required=approval_required,
    )


def _new_run(
    *,
    campaign: Campaign,
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
    output: GovernedIntelligenceBrief,
    provider_state: str,
    error_code: str,
    rejection_reason: str,
    now: datetime,
) -> None:
    row.status = "fallback"
    row.provider_state = provider_state
    row.output_payload = output.model_dump(mode="json")
    row.selected_action_id = output.selected_action_id
    row.error_code = error_code
    row.rejection_reason = rejection_reason[:2000]
    row.completed_at = now
    logger.warning(
        "Governed AI request fell back to the deterministic brief",
        extra={
            "organization_id": row.organization_id,
            "campaign_id": row.campaign_id,
            "provider_name": row.provider_name,
            "model_name": row.model_name,
            "provider_state": provider_state,
            "error_code": error_code,
            "run_id": row.id,
        },
    )
    db.commit()
    db.refresh(row)


def _run_payload(db: Session, row: GovernedAIRun) -> dict[str, Any]:
    lexicon = get_active_lexicon(db, tenant_id=row.tenant_id)
    action = (
        lexicon.action_index.get(row.selected_action_id)
        if row.selected_action_id
        else None
    )
    output = dict(row.output_payload or {})
    output["selected_action"] = (
        {
            "action_id": action.action_id,
            "display_name": action.display_name,
            "why_it_matters": action.why_it_matters,
            "steps": list(action.steps),
            "risk_tier": action.risk_tier,
            "effort": action.effort,
            "approval_required": action.risk_tier >= 2,
        }
        if action is not None
        else None
    )
    daily_action_ids = [
        str(item)
        for item in (output.get("daily_action_ids") or [])
        if str(item)
    ]
    if not daily_action_ids and row.selected_action_id:
        daily_action_ids = [row.selected_action_id]
    output["daily_action_ids"] = daily_action_ids[:DAILY_ACTION_LIMIT]
    output["daily_actions"] = [
        {
            "action_id": daily_action.action_id,
            "display_name": daily_action.display_name,
            "why_it_matters": daily_action.why_it_matters,
            "steps": list(daily_action.steps),
            "risk_tier": daily_action.risk_tier,
            "effort": str(daily_action.effort),
            "approval_required": daily_action.risk_tier >= 2,
        }
        for action_id in output["daily_action_ids"]
        if (daily_action := lexicon.action_index.get(action_id)) is not None
    ]
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
        "evidence_count": len(row.evidence_refs or []),
        "error_code": row.error_code,
        "rejection_reason": row.rejection_reason,
        "created_at": row.created_at.isoformat(),
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
        "truth": {
            "classification": (
                "generated" if row.status == "validated" else "heuristic"
            ),
            "states": (
                ["generated", "operator_review_required"]
                if row.status == "validated"
                else ["heuristic", "operator_review_required"]
            ),
            "provider_state": row.provider_state,
            "operator_state": "operator_review_required",
            "summary": (
                "Mistral explained the deterministic daily plan without changing its evidence, actions, risk, or approval requirements."
                if row.status == "validated"
                else "The deterministic daily plan remains available without an AI-generated explanation."
            ),
            "reasons": [
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
        "item": _run_payload(db, row),
        "runtime": _runtime_status(),
        "allowance": _action_allowance(db, organization_id=row.organization_id),
        "idempotent_replay": idempotent_replay,
    }


def _runtime_status() -> dict[str, Any]:
    settings = get_settings()
    backend = settings.ai_provider_backend.strip().lower()
    configured = backend == "mistral" and bool(settings.mistral_api_key.strip())
    return {
        "backend": backend or "disabled",
        "model": settings.mistral_model,
        "configured": configured,
        "decision_authority": "deterministic_engine",
        "ai_role": "explain_bounded_daily_plan",
        "automatic_execution": False,
    }


def _action_allowance(
    db: Session,
    *,
    organization_id: str,
) -> dict[str, Any]:
    plan = cost_economics_service.resolve_plan_economics(
        _organization_plan_type(db, organization_id)
    )
    limit = MONTHLY_ACTION_LIMITS[plan.code]
    used = _provider_actions_used(
        db,
        organization_id=organization_id,
        now=datetime.now(UTC),
    )
    return {
        "monthly_actions": limit,
        "used": used,
        "remaining": max(0, limit - used),
    }


def _provider_actions_used(
    db: Session,
    *,
    organization_id: str,
    now: datetime,
) -> int:
    period_start, period_end = cost_economics_service.period_bounds(now)
    return int(
        db.query(func.count(GovernedAIRun.id))
        .filter(
            GovernedAIRun.organization_id == organization_id,
            GovernedAIRun.cost_reservation_id.is_not(None),
            GovernedAIRun.created_at >= period_start,
            GovernedAIRun.created_at < period_end,
        )
        .scalar()
        or 0
    )


def _organization_plan_type(db: Session, organization_id: str) -> str:
    from app.models.organization import Organization

    organization = db.get(Organization, organization_id)
    if organization is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    return organization.plan_type


def _campaign_for_organization(
    db: Session,
    *,
    organization_id: str,
    campaign_id: str,
) -> Campaign:
    campaign = db.get(Campaign, campaign_id)
    matches_scope = bool(
        campaign
        and (
            campaign.organization_id == organization_id
            or (
                campaign.organization_id is None
                and campaign.tenant_id == organization_id
            )
        )
    )
    if campaign is None or not matches_scope:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


def _run_by_key(
    db: Session,
    *,
    organization_id: str,
    idempotency_key: str,
) -> GovernedAIRun | None:
    return (
        db.query(GovernedAIRun)
        .filter(
            GovernedAIRun.organization_id == organization_id,
            GovernedAIRun.idempotency_key == idempotency_key,
        )
        .first()
    )


def _validated_retry_for_key(
    db: Session,
    *,
    organization_id: str,
    idempotency_key: str,
) -> GovernedAIRun | None:
    return (
        db.query(GovernedAIRun)
        .filter(
            GovernedAIRun.organization_id == organization_id,
            GovernedAIRun.idempotency_key.like(f"{idempotency_key}:retry:%"),
            GovernedAIRun.status == "validated",
        )
        .order_by(GovernedAIRun.completed_at.desc())
        .first()
    )


def _commit_new_run(
    db: Session,
    row: GovernedAIRun,
) -> GovernedAIRun | None:
    try:
        db.commit()
        return None
    except IntegrityError:
        db.rollback()
        concurrent = _run_by_key(
            db,
            organization_id=row.organization_id,
            idempotency_key=row.idempotency_key,
        )
        if concurrent is not None:
            return concurrent
        raise


def _already_running_error() -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={
            "message": "An AI explanation is already being prepared for this account.",
            "reason_code": "ai_concurrency_limit",
        },
    )


def _hash_payload(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)

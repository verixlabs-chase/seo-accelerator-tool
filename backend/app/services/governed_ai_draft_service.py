from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
import json
import logging
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.intelligence.contracts.governed_ai import (
    DRAFT_LIMITS,
    GovernedActionDraft,
)
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
    GovernedAIDraftProvider,
    GovernedAIProviderError,
    MistralGovernedAIProvider,
)


FEATURE = "intelligence_draft"
PROMPT_TEMPLATE_VERSION = "insightos-governed-action-draft-v1"
MISTRAL_OPERATION = governed_ai_service.MISTRAL_OPERATION
logger = logging.getLogger(__name__)

DRAFT_TYPE_DETAILS: dict[str, dict[str, str]] = {
    "search_result": {
        "label": "Search-result wording",
        "description": "Draft a page title and short description for review.",
        "title_label": "Suggested page title",
        "body_label": "Suggested description",
    },
    "review_request": {
        "label": "Customer review request",
        "description": "Draft a simple request for recent customers.",
        "title_label": "Suggested subject",
        "body_label": "Suggested message",
    },
    "review_response": {
        "label": "Review response",
        "description": "Draft a careful response template for review.",
        "title_label": "Response purpose",
        "body_label": "Suggested response",
    },
    "page_outline": {
        "label": "Helpful page outline",
        "description": "Draft a plain-language page structure for review.",
        "title_label": "Suggested page heading",
        "body_label": "Suggested outline",
    },
}

SEARCH_RESULT_ACTIONS = {
    "organic.rewrite_search_snippet",
    "organic.align_snippet_intent",
    "competitive.benchmark_snippets",
    "organic.strengthen_value_proposition",
}
REVIEW_REQUEST_ACTIONS = {
    "reputation.launch_review_request_workflow",
    "reputation.expand_review_request_coverage",
    "reputation.increase_review_volume",
    "reputation.restore_review_momentum",
    "reputation.automate_review_reminders",
}
REVIEW_RESPONSE_ACTIONS = {
    "reputation.create_response_sla",
    "reputation.review_response_backlog",
}
PAGE_OUTLINE_ACTIONS = {
    "organic.refresh_affected_pages",
    "competitive.refresh_gap_pages",
    "competitive.improve_intent_and_links",
    "organic.reinforce_declining_clusters",
    "content.restore_editorial_cadence",
    "content.reprioritize_backlog",
    "refresh_declining_pages",
    "expand_supporting_content",
    "publish_cluster_support_pages",
}


def list_governed_drafts(
    db: Session,
    *,
    organization_id: str,
    campaign_id: str,
    limit: int = 10,
) -> dict[str, Any]:
    campaign, context_bundle = _campaign_draft_context(
        db,
        organization_id=organization_id,
        campaign_id=campaign_id,
        now=datetime.now(UTC),
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
        "available_actions": _available_actions(context_bundle["context"]),
        "runtime": _runtime_status(),
        "allowance": governed_ai_service._action_allowance(
            db,
            organization_id=organization_id,
        ),
    }


def generate_governed_draft(
    db: Session,
    *,
    organization_id: str,
    campaign_id: str,
    requested_by_user_id: str | None,
    action_id: str,
    draft_type: str,
    refresh: bool = False,
    retry_failed: bool = False,
    provider: GovernedAIDraftProvider | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    occurred_at = governed_ai_service._as_utc(now or datetime.now(UTC))
    selected_action_id = action_id.strip()
    selected_draft_type = draft_type.strip().lower()
    if not selected_action_id:
        raise HTTPException(status_code=422, detail="Choose a saved action first.")
    if selected_draft_type not in DRAFT_TYPE_DETAILS:
        raise HTTPException(status_code=422, detail="Choose a supported draft type.")

    settings = get_settings()
    campaign, context_bundle = _campaign_draft_context(
        db,
        organization_id=organization_id,
        campaign_id=campaign_id,
        now=occurred_at,
    )
    available = {
        str(item["action_id"]): item
        for item in _available_actions(context_bundle["context"])
    }
    selected = available.get(selected_action_id)
    if selected is None:
        raise HTTPException(
            status_code=422,
            detail="Drafting is not available for that saved action.",
        )
    allowed_draft_types = {
        str(item["draft_type"]) for item in selected["draft_types"]
    }
    if selected_draft_type not in allowed_draft_types:
        raise HTTPException(
            status_code=422,
            detail="That draft type is not available for the selected action.",
        )

    context, evidence_ids = _narrow_draft_context(
        context_bundle["context"],
        action_id=selected_action_id,
        draft_type=selected_draft_type,
    )
    context_hash = governed_ai_service._hash_payload(context)
    prompt_hash = governed_ai_service._hash_payload(
        {
            "template_version": PROMPT_TEMPLATE_VERSION,
            "schema": GovernedActionDraft.model_json_schema(),
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
            "action_id": selected_action_id,
            "draft_type": selected_draft_type,
            "context_hash": context_hash,
            "prompt_hash": prompt_hash,
            "model_name": model_name,
            "provider_configured": provider_configured,
            "period": occurred_at.strftime("%Y-%m"),
            "day": occurred_at.strftime("%Y-%m-%d"),
        }
    )
    idempotency_key = f"ai:{FEATURE}:{idempotency_base}"
    refresh_bucket = occurred_at.replace(
        minute=(occurred_at.minute // 15) * 15,
        second=0,
        microsecond=0,
    )
    if refresh:
        idempotency_key = f"{idempotency_key}:refresh:{refresh_bucket.isoformat()}"

    existing = governed_ai_service._run_by_key(
        db,
        organization_id=organization_id,
        idempotency_key=idempotency_key,
    )
    if existing is not None:
        if existing.status == "running":
            raise governed_ai_service._already_running_error()
        if existing.status == "validated":
            return _response(
                db,
                existing,
                available_actions=list(available.values()),
                idempotent_replay=True,
            )
        if not retry_failed:
            recovered = governed_ai_service._validated_retry_for_key(
                db,
                organization_id=organization_id,
                idempotency_key=idempotency_key,
            )
            return _response(
                db,
                recovered or existing,
                available_actions=list(available.values()),
                idempotent_replay=True,
            )
        idempotency_key = f"{idempotency_key}:retry:{refresh_bucket.isoformat()}"
        retry_existing = governed_ai_service._run_by_key(
            db,
            organization_id=organization_id,
            idempotency_key=idempotency_key,
        )
        if retry_existing is not None:
            return _response(
                db,
                retry_existing,
                available_actions=list(available.values()),
                idempotent_replay=True,
            )

    fallback = _fallback_draft(
        action_id=selected_action_id,
        draft_type=selected_draft_type,
    )
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
            lexicon=context_bundle["lexicon"],
            context_hash=context_hash,
            prompt_hash=prompt_hash,
            idempotency_key=idempotency_key,
            action_id=selected_action_id,
            evidence_ids=evidence_ids,
            now=occurred_at,
        )
        db.add(row)
        concurrent = governed_ai_service._commit_new_run(db, row)
        if concurrent is not None:
            return _response(
                db,
                concurrent,
                available_actions=list(available.values()),
                idempotent_replay=True,
            )
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
        return _response(
            db,
            row,
            available_actions=list(available.values()),
            idempotent_replay=False,
        )

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
        provider_name=(
            provider.name if provider is not None else (backend or "deterministic")
        ),
        model_name=provider.model_name if provider is not None else model_name,
        lexicon=context_bundle["lexicon"],
        context_hash=context_hash,
        prompt_hash=prompt_hash,
        idempotency_key=idempotency_key,
        action_id=selected_action_id,
        evidence_ids=evidence_ids,
        now=occurred_at,
    )
    db.add(row)
    concurrent = governed_ai_service._commit_new_run(db, row)
    if concurrent is not None:
        if concurrent.status == "running":
            raise governed_ai_service._already_running_error()
        return _response(
            db,
            concurrent,
            available_actions=list(available.values()),
            idempotent_replay=True,
        )
    db.refresh(row)

    context_json = json.dumps(context, sort_keys=True, separators=(",", ":"))
    language_guide = load_service_business_language_guide()
    estimated_input_tokens = max(
        1,
        (len(context_json) + len(language_guide) + 3) // 4 + 320,
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
        return _response(
            db,
            row,
            available_actions=list(available.values()),
            idempotent_replay=False,
        )

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
        return _response(
            db,
            row,
            available_actions=list(available.values()),
            idempotent_replay=False,
        )

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
            return _response(
                db,
                row,
                available_actions=list(available.values()),
                idempotent_replay=False,
            )
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
        return _response(
            db,
            row,
            available_actions=list(available.values()),
            idempotent_replay=False,
        )

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
        return _response(
            db,
            row,
            available_actions=list(available.values()),
            idempotent_replay=False,
        )

    try:
        provider_response = provider.draft_action(
            context=context,
            output_schema=GovernedActionDraft.model_json_schema(),
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
            row.reconciled_cost = (
                terminal.provider_reported_cost or reservation.estimated_cost
            )
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
        return _response(
            db,
            row,
            available_actions=list(available.values()),
            idempotent_replay=False,
        )
    except Exception:
        logger.exception(
            "Unexpected governed AI draft failure",
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
            rejection_reason="The AI provider could not complete the draft.",
            now=occurred_at,
        )
        return _response(
            db,
            row,
            available_actions=list(available.values()),
            idempotent_replay=False,
        )

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
        return _response(
            db,
            row,
            available_actions=list(available.values()),
            idempotent_replay=False,
        )

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
        output = GovernedActionDraft.model_validate(provider_response.payload)
        output.validate_against_context(
            requested_action_id=selected_action_id,
            requested_draft_type=selected_draft_type,
            evidence_ids=set(evidence_ids),
            allowed_action_ids={selected_action_id},
            allowed_draft_types=allowed_draft_types,
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
        return _response(
            db,
            row,
            available_actions=list(available.values()),
            idempotent_replay=False,
        )

    row.status = "validated"
    row.provider_state = "ready"
    row.output_payload = _output_payload(output, context=context)
    row.selected_action_id = selected_action_id
    row.completed_at = occurred_at
    db.commit()
    db.refresh(row)
    return _response(
        db,
        row,
        available_actions=list(available.values()),
        idempotent_replay=False,
    )


def _campaign_draft_context(
    db: Session,
    *,
    organization_id: str,
    campaign_id: str,
    now: datetime,
) -> tuple[Any, dict[str, Any]]:
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
        now=now,
    )
    context_bundle = governed_ai_service._build_context(
        campaign=campaign,
        score=score,
        recommendations=recommendations,
        lexicon=lexicon,
        action_plans=action_plans,
        work_items=work_items,
    )
    context_bundle["lexicon"] = lexicon
    return campaign, context_bundle


def _available_actions(context: dict[str, Any]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for action in context.get("allowed_actions") or []:
        if not isinstance(action, dict) or not action.get("action_id"):
            continue
        action_id = str(action["action_id"])
        draft_types = [
            {
                "draft_type": item,
                **DRAFT_TYPE_DETAILS[item],
                "title_max_characters": DRAFT_LIMITS[item]["title"],
                "body_max_characters": DRAFT_LIMITS[item]["body"],
            }
            for item in _allowed_draft_types(action_id)
        ]
        if not draft_types:
            continue
        results.append(
            {
                "action_id": action_id,
                "display_name": action.get("display_name"),
                "why_it_matters": action.get("why_it_matters"),
                "draft_types": draft_types,
            }
        )
    return results


def _allowed_draft_types(action_id: str) -> list[str]:
    results: list[str] = []
    if action_id in SEARCH_RESULT_ACTIONS:
        results.append("search_result")
    if action_id in REVIEW_REQUEST_ACTIONS:
        results.append("review_request")
    if action_id in REVIEW_RESPONSE_ACTIONS:
        results.append("review_response")
    if action_id in PAGE_OUTLINE_ACTIONS:
        results.append("page_outline")
    return results


def _narrow_draft_context(
    raw_context: dict[str, Any],
    *,
    action_id: str,
    draft_type: str,
) -> tuple[dict[str, Any], list[str]]:
    context = dict(raw_context)
    facts = raw_context.get("facts") if isinstance(raw_context.get("facts"), dict) else {}
    campaign_fact = facts.get("campaign") if isinstance(facts.get("campaign"), dict) else {}
    related_recommendations = [
        item
        for item in (facts.get("recommendations") or [])
        if isinstance(item, dict)
        and isinstance(item.get("action_plan"), dict)
        and str(item["action_plan"].get("action_id") or "") == action_id
    ]
    selected_actions = [
        item
        for item in (raw_context.get("allowed_actions") or [])
        if isinstance(item, dict) and str(item.get("action_id") or "") == action_id
    ]
    evidence_ids = []
    if campaign_fact.get("evidence_id"):
        evidence_ids.append(str(campaign_fact["evidence_id"]))
    evidence_ids.extend(
        str(item["evidence_id"])
        for item in related_recommendations
        if item.get("evidence_id")
    )
    context["contract"] = {
        **dict(raw_context.get("contract") or {}),
        "ai_role": "draft_copy_for_saved_action_only",
    }
    context["facts"] = {
        "campaign": campaign_fact,
        "recommendations": related_recommendations,
    }
    context["allowed_actions"] = selected_actions
    context["allowed_evidence_ids"] = evidence_ids
    context["draft_request"] = {
        "action_id": action_id,
        "draft_type": draft_type,
        "approval_required": True,
        "title_max_characters": DRAFT_LIMITS[draft_type]["title"],
        "body_max_characters": DRAFT_LIMITS[draft_type]["body"],
        "title_label": DRAFT_TYPE_DETAILS[draft_type]["title_label"],
        "body_label": DRAFT_TYPE_DETAILS[draft_type]["body_label"],
        "may_execute_changes": False,
        "may_introduce_numeric_claims": False,
        "unsupported_fact_policy": "return_not_enough_information",
    }
    context["required_output"] = {
        "action_id": "copy draft_request.action_id exactly",
        "draft_type": "copy draft_request.draft_type exactly",
        "draft_state": "ready only when supplied evidence supports truthful copy",
        "title": DRAFT_TYPE_DETAILS[draft_type]["title_label"],
        "body": DRAFT_TYPE_DETAILS[draft_type]["body_label"],
        "evidence_used": "IDs from allowed_evidence_ids only",
        "uncertainties": "facts the customer must confirm before approval",
        "approval_required": True,
    }
    return context, evidence_ids


def _fallback_draft(*, action_id: str, draft_type: str) -> GovernedActionDraft:
    return GovernedActionDraft(
        action_id=action_id,
        draft_type=draft_type,
        draft_state="temporarily_unavailable",
        title="Draft temporarily unavailable",
        body=(
            "Use the saved checklist while the writing service is unavailable. "
            "Nothing was changed or published."
        ),
        evidence_used=[],
        uncertainties=[
            "No generated wording was accepted, so the saved action remains unchanged."
        ],
        approval_required=True,
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
    action_id: str,
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
        selected_action_id=action_id,
        allowed_action_ids=[action_id],
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
    output: GovernedActionDraft,
    provider_state: str,
    error_code: str,
    rejection_reason: str,
    now: datetime,
) -> None:
    details = DRAFT_TYPE_DETAILS[output.draft_type]
    output_payload = output.model_dump(mode="json")
    output_payload["draft_type_label"] = details["label"]
    output_payload["title_label"] = details["title_label"]
    output_payload["body_label"] = details["body_label"]
    output_payload["evidence_details"] = []
    row.status = "fallback"
    row.provider_state = provider_state
    row.output_payload = output_payload
    row.error_code = error_code
    row.rejection_reason = rejection_reason[:2000]
    row.completed_at = now
    db.commit()
    db.refresh(row)


def _output_payload(
    output: GovernedActionDraft,
    *,
    context: dict[str, Any],
) -> dict[str, Any]:
    payload = output.model_dump(mode="json")
    details = DRAFT_TYPE_DETAILS[output.draft_type]
    payload["draft_type_label"] = details["label"]
    payload["title_label"] = details["title_label"]
    payload["body_label"] = details["body_label"]
    payload["evidence_details"] = _evidence_details(
        context,
        evidence_used=output.evidence_used,
    )
    # Keep the exact bounded input that produced accepted copy. The row-level
    # context hash proves this snapshot was not substituted later, while the
    # snapshot makes every business fact and cited evidence replayable without
    # relying on mutable campaign records.
    payload["input_snapshot"] = context
    payload["lineage_schema_version"] = "governed-copy-lineage-v1"
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
    for recommendation in facts.get("recommendations") or []:
        if not isinstance(recommendation, dict) or not recommendation.get("evidence_id"):
            continue
        plan = recommendation.get("action_plan") or {}
        candidates[str(recommendation["evidence_id"])] = {
            "evidence_id": str(recommendation["evidence_id"]),
            "label": simplify_internal_language(
                str(plan.get("display_name") or "Saved action"),
                max_words=14,
                max_sentences=1,
                action_first=False,
            )
            or "Saved action",
            "detail": simplify_internal_language(
                str(recommendation.get("rationale") or "Saved location information"),
                max_words=28,
                max_sentences=2,
                action_first=False,
            )
            or "Saved location information",
            "captured_at": recommendation.get("created_at"),
        }
    return [candidates[item] for item in evidence_used if item in candidates]


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
                ["generated", "operator_review_required"]
                if row.status == "validated"
                else ["heuristic", "operator_review_required"]
            ),
            "provider_state": row.provider_state,
            "operator_state": "operator_review_required",
            "summary": (
                "AI drafted review-only wording for one saved action using cited location information."
                if row.status == "validated"
                else "No generated wording was accepted; the saved action remains unchanged."
            ),
            "reasons": [
                "saved_action_controls_draft_scope",
                "saved_evidence_is_the_only_fact_source",
                "customer_review_is_required",
                "no_automatic_site_or_profile_changes",
            ],
        },
    }


def _response(
    db: Session,
    row: GovernedAIRun,
    *,
    available_actions: list[dict[str, Any]],
    idempotent_replay: bool,
) -> dict[str, Any]:
    return {
        "item": _run_payload(row),
        "available_actions": available_actions,
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
        "ai_role": "draft_copy_for_saved_action_only",
        "automatic_execution": False,
    }

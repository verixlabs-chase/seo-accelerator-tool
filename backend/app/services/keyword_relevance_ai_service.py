from __future__ import annotations

from dataclasses import dataclass
import json
import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from time import perf_counter
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.intelligence.contracts.governed_ai import GovernedKeywordRelevanceReview
from app.intelligence.lexicon.loader import get_active_lexicon
from app.intelligence.lexicon.plain_language import (
    SERVICE_BUSINESS_LANGUAGE_GUIDE_VERSION,
    load_service_business_language_guide,
    service_business_language_guide_hash,
)
from app.models.campaign import Campaign
from app.models.governed_ai import GovernedAIRun
from app.models.keyword_research import KeywordResearchRun, KeywordResearchSuggestion
from app.services import (
    business_service_area_service,
    business_service_service,
    cost_economics_service,
    governed_ai_service,
    keyword_research_service,
)
from app.services.governed_ai_provider import (
    GovernedAIKeywordRelevanceProvider,
    GovernedAIProviderError,
    MistralGovernedAIProvider,
)
from app.services.governed_ai_provider_capability_service import CapabilitySelection
from app.services.governed_ai_provider_connection_service import (
    GovernedAIProviderConnectionError,
    open_pinned_runtime_provider,
)
from app.services.governed_ai_provider_keyword_capability_service import (
    automatic_keyword_review_rollback,
    authorize_keyword_review_dispatch,
    record_keyword_review_fallback,
    record_keyword_review_success,
    select_keyword_review_capability,
)


FEATURE = "keyword_relevance_review"
PROMPT_TEMPLATE_VERSION = "insightos-keyword-relevance-review-v1"
MISTRAL_CAPABILITY = "governed_ai"
MISTRAL_OPERATION = "keyword_relevance_review"
ACCEPTANCE_CONFIDENCE = 0.8
logger = logging.getLogger(__name__)


@dataclass
class _PrivateKeywordReviewResult:
    event: Any | None = None
    output: GovernedKeywordRelevanceReview | None = None
    provider_response: Any | None = None
    provider_name: str = "private_ai"
    model_name: str = ""
    prompt_attempted: bool = False
    error_code: str | None = None
    provider_may_have_processed: bool = False
    input_tokens: int = 0
    output_tokens: int = 0
    duration_ms: int = 0


def review_uncertain(
    db: Session,
    *,
    tenant_id: str,
    campaign_id: str,
    requested_by_user_id: str | None,
    max_items: int = 8,
    retry_failed: bool = False,
    provider: GovernedAIKeywordRelevanceProvider | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    occurred_at = governed_ai_service._as_utc(now or datetime.now(UTC))
    campaign = _campaign_or_404(db, tenant_id=tenant_id, campaign_id=campaign_id)
    research_run = (
        db.query(KeywordResearchRun)
        .filter(
            KeywordResearchRun.tenant_id == tenant_id,
            KeywordResearchRun.campaign_id == campaign.id,
        )
        .order_by(KeywordResearchRun.created_at.desc())
        .first()
    )
    if research_run is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Find customer searches before reviewing unclear results.",
        )
    candidates = (
        db.query(KeywordResearchSuggestion)
        .filter(
            KeywordResearchSuggestion.run_id == research_run.id,
            KeywordResearchSuggestion.tenant_id == tenant_id,
            KeywordResearchSuggestion.relevance_status == "needs_review",
            KeywordResearchSuggestion.ai_review_status != "validated",
            KeywordResearchSuggestion.dismissed_at.is_(None),
        )
        .order_by(
            KeywordResearchSuggestion.opportunity_score.desc(),
            KeywordResearchSuggestion.keyword.asc(),
        )
        .limit(max(1, min(max_items, 12)))
        .all()
    )
    if not candidates:
        return _response(
            db,
            campaign=campaign,
            run=None,
            review={
                "state": "nothing_to_review",
                "reviewed": 0,
                "best_matches": 0,
                "hidden_unrelated": 0,
                "still_unclear": 0,
                "message": "There are no unclear searches waiting for review.",
            },
            idempotent_replay=False,
        )

    services = business_service_service.confirmed_services_for_campaign(
        db, tenant_id=tenant_id, campaign_id=campaign.id
    )
    included_areas, excluded_areas = (
        business_service_area_service.confirmed_areas_for_campaign(
            db, tenant_id=tenant_id, campaign_id=campaign.id
        )
    )
    if not services or not included_areas:
        missing = []
        if not services:
            missing.append("the work this location offers")
        if not included_areas:
            missing.append("where this location takes jobs")
        return _response(
            db,
            campaign=campaign,
            run=None,
            review={
                "state": "needs_setup",
                "reviewed": 0,
                "best_matches": 0,
                "hidden_unrelated": 0,
                "still_unclear": len(candidates),
                "message": f"Confirm {' and '.join(missing)} before using AI review.",
            },
            idempotent_replay=False,
        )

    context, evidence_ids = _build_context(
        campaign=campaign,
        candidates=candidates,
        services=services,
        included_areas=included_areas,
        excluded_areas=excluded_areas,
    )
    context_hash = governed_ai_service._hash_payload(context)
    prompt_hash = governed_ai_service._hash_payload(
        {
            "template_version": PROMPT_TEMPLATE_VERSION,
            "schema": GovernedKeywordRelevanceReview.model_json_schema(),
            "writing_guide_version": SERVICE_BUSINESS_LANGUAGE_GUIDE_VERSION,
            "writing_guide_hash": service_business_language_guide_hash(),
            "acceptance_confidence": ACCEPTANCE_CONFIDENCE,
        }
    )
    settings = get_settings()
    backend = settings.ai_provider_backend.strip().lower()
    model_name = settings.mistral_model.strip() or "mistral-small-2603"
    provider_configured = provider is not None or (
        backend == "mistral" and bool(settings.mistral_api_key.strip())
    )
    idempotency_base = governed_ai_service._hash_payload(
        {
            "organization_id": campaign.organization_id,
            "campaign_id": campaign.id,
            "feature": FEATURE,
            "context_hash": context_hash,
            "prompt_hash": prompt_hash,
            "model_name": provider.model_name if provider is not None else model_name,
        }
    )
    idempotency_key = f"ai:{FEATURE}:{idempotency_base}"
    existing = governed_ai_service._run_by_key(
        db,
        organization_id=str(campaign.organization_id),
        idempotency_key=idempotency_key,
    )
    if existing is not None:
        if existing.status == "running":
            raise governed_ai_service._already_running_error()
        if existing.status == "validated" or not retry_failed:
            return _response(
                db,
                campaign=campaign,
                run=existing,
                review=_review_summary(existing),
                idempotent_replay=True,
            )
        retry_bucket = occurred_at.replace(
            minute=(occurred_at.minute // 15) * 15,
            second=0,
            microsecond=0,
        )
        idempotency_key = f"{idempotency_key}:retry:{retry_bucket.isoformat()}"
        retry_existing = governed_ai_service._run_by_key(
            db,
            organization_id=str(campaign.organization_id),
            idempotency_key=idempotency_key,
        )
        if retry_existing is not None:
            return _response(
                db,
                campaign=campaign,
                run=retry_existing,
                review=_review_summary(retry_existing),
                idempotent_replay=True,
            )

    capability_selection = (
        select_keyword_review_capability(
            db,
            organization_id=str(campaign.organization_id),
            request_key=idempotency_key,
            now=occurred_at,
        )
        if provider is None and provider_configured
        else None
    )

    plan = cost_economics_service.resolve_plan_economics(
        governed_ai_service._organization_plan_type(db, str(campaign.organization_id))
    )
    action_limit = governed_ai_service.MONTHLY_ACTION_LIMITS[plan.code]
    actions_used = governed_ai_service._provider_actions_used(
        db, organization_id=str(campaign.organization_id), now=occurred_at
    )
    if actions_used >= action_limit:
        return _fallback_run_response(
            db,
            campaign=campaign,
            requested_by_user_id=requested_by_user_id,
            provider_name=backend or "deterministic",
            model_name=model_name,
            context_hash=context_hash,
            prompt_hash=prompt_hash,
            idempotency_key=idempotency_key,
            suggestion_ids=[row.id for row in candidates],
            evidence_ids=evidence_ids,
            provider_state="allowance_exhausted",
            error_code="ai_action_allowance_exhausted",
            message="This account has used its AI reviews for the month. Your saved search list was not changed.",
            now=occurred_at,
        )

    concurrency_limit = governed_ai_service.CONCURRENCY_LIMITS[plan.code]
    running = (
        db.query(func.count(GovernedAIRun.id))
        .filter(
            GovernedAIRun.organization_id == campaign.organization_id,
            GovernedAIRun.status == "running",
            GovernedAIRun.created_at >= occurred_at - timedelta(minutes=5),
        )
        .scalar()
        or 0
    )
    if running >= concurrency_limit:
        raise governed_ai_service._already_running_error()

    lexicon = get_active_lexicon(db, tenant_id=tenant_id)
    ai_run = GovernedAIRun(
        tenant_id=tenant_id,
        organization_id=str(campaign.organization_id),
        campaign_id=campaign.id,
        business_location_id=campaign.business_location_id,
        requested_by_user_id=requested_by_user_id,
        feature=FEATURE,
        provider_name=provider.name if provider is not None else (backend or "deterministic"),
        model_name=provider.model_name if provider is not None else model_name,
        prompt_template_version=PROMPT_TEMPLATE_VERSION,
        lexicon_id=lexicon.meta.lexicon_id,
        lexicon_version=lexicon.meta.version,
        context_hash=context_hash,
        prompt_hash=prompt_hash,
        idempotency_key=idempotency_key,
        status="running",
        provider_state="pending",
        allowed_action_ids=[row.id for row in candidates],
        evidence_refs=evidence_ids,
        output_payload={},
        input_tokens=0,
        output_tokens=0,
        estimated_cost=Decimal("0"),
        reconciled_cost=Decimal("0"),
        created_at=occurred_at,
    )
    db.add(ai_run)
    concurrent = governed_ai_service._commit_new_run(db, ai_run)
    if concurrent is not None:
        if concurrent.status == "running":
            raise governed_ai_service._already_running_error()
        return _response(
            db,
            campaign=campaign,
            run=concurrent,
            review=_review_summary(concurrent),
            idempotent_replay=True,
        )
    db.refresh(ai_run)

    context_json = json.dumps(context, sort_keys=True, separators=(",", ":"))
    language_guide = load_service_business_language_guide()
    estimated_input_tokens = max(
        1,
        (len(context_json) + len(language_guide) + 3) // 4 + 300,
    )
    if estimated_input_tokens > settings.ai_max_input_tokens:
        return _finalize_fallback(
            db,
            campaign=campaign,
            run=ai_run,
            provider_state="context_rejected",
            error_code="ai_context_too_large",
            message="There were too many details to review safely. Your saved search list was not changed.",
            now=occurred_at,
        )
    if not provider_configured:
        return _finalize_fallback(
            db,
            campaign=campaign,
            run=ai_run,
            provider_state="not_configured",
            error_code="ai_provider_not_configured",
            message="AI review is not connected yet. Your saved search list was not changed.",
            now=occurred_at,
        )
    if provider is None:
        if backend != "mistral":
            return _finalize_fallback(
                db,
                campaign=campaign,
                run=ai_run,
                provider_state="not_configured",
                error_code="ai_provider_backend_unsupported",
                message="AI review is not available. Your saved search list was not changed.",
                now=occurred_at,
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
            organization_id=str(campaign.organization_id),
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
        return _finalize_fallback(
            db,
            campaign=campaign,
            run=ai_run,
            provider_state=(
                "allowance_exhausted"
                if isinstance(exc, cost_economics_service.CostAllowanceExceeded)
                else "cost_control_blocked"
            ),
            error_code=exc.reason_code,
            message="AI review was skipped to protect this account's usage allowance. Nothing changed.",
            now=occurred_at,
        )

    ai_run.cost_reservation_id = reservation.id
    ai_run.price_card_version = reservation.price_card_version
    ai_run.estimated_cost = reservation.estimated_cost
    db.commit()

    try:
        cost_economics_service.authorize_reserved_provider_dispatch(
            db,
            reservation=reservation,
        )
    except cost_economics_service.CostEconomicsError as exc:
        return _finalize_fallback(
            db,
            campaign=campaign,
            run=ai_run,
            provider_state="cost_control_blocked",
            error_code=exc.reason_code,
            message="AI review was skipped because this location is not currently eligible for paid updates. Nothing changed.",
            now=occurred_at,
        )

    private_result = None
    if capability_selection is not None:
        private_result = _attempt_private_keyword_review(
            db,
            organization_id=str(campaign.organization_id),
            selection=capability_selection,
            request_key=idempotency_key,
            context=context,
            suggestion_ids={row.id for row in candidates},
            service_ids={row.id for row in services},
            included_area_ids={row.id for row in included_areas},
            excluded_area_ids={row.id for row in excluded_areas},
            evidence_ids=set(evidence_ids),
            timeout_seconds=settings.ai_provider_timeout_seconds,
            max_output_tokens=settings.ai_max_output_tokens,
            now=occurred_at,
        )
        if private_result.output is not None and private_result.provider_response is not None:
            cost_economics_service.release_provider_cost(
                db,
                reservation=reservation,
                now=occurred_at,
            )
            ai_run.provider_name = private_result.provider_name
            ai_run.model_name = private_result.model_name
            ai_run.input_tokens = private_result.input_tokens
            ai_run.output_tokens = private_result.output_tokens
            ai_run.estimated_cost = Decimal("0")
            ai_run.reconciled_cost = Decimal("0")
            ai_run.price_card_version = None
            ai_run.provider_request_id = (
                private_result.provider_response.provider_request_id
            )
            ai_run.response_hash = governed_ai_service._hash_payload(
                private_result.provider_response.payload
            )
            counts = _apply_validated_review(
                candidates=candidates,
                output=private_result.output,
                services=services,
                included_areas=included_areas,
                excluded_areas=excluded_areas,
                run=ai_run,
                now=occurred_at,
            )
            ai_run.status = "validated"
            ai_run.provider_state = "ready"
            ai_run.output_payload = {
                **private_result.output.model_dump(mode="json"),
                "summary": counts,
                "message": _counts_message(counts),
            }
            ai_run.completed_at = occurred_at
            db.commit()
            db.refresh(ai_run)
            return _response(
                db,
                campaign=campaign,
                run=ai_run,
                review=_review_summary(ai_run),
                idempotent_replay=False,
            )

    ai_run.provider_name = provider.name
    ai_run.model_name = provider.model_name

    try:
        provider_response = provider.review_keyword_relevance(
            context=context,
            output_schema=GovernedKeywordRelevanceReview.model_json_schema(),
            prompt_template_version=PROMPT_TEMPLATE_VERSION,
        )
    except GovernedAIProviderError as exc:
        _record_private_keyword_review_fallback(
            db,
            result=private_result,
            request_key=idempotency_key,
            managed_succeeded=False,
            now=occurred_at,
        )
        if exc.provider_may_have_processed:
            terminal = cost_economics_service.reconcile_provider_cost(
                db,
                reservation=reservation,
                provider_reported_cost=reservation.estimated_cost,
                now=occurred_at,
            )
            ai_run.reconciled_cost = terminal.provider_reported_cost or reservation.estimated_cost
        else:
            cost_economics_service.release_provider_cost(
                db, reservation=reservation, now=occurred_at
            )
        return _finalize_fallback(
            db,
            campaign=campaign,
            run=ai_run,
            provider_state="unavailable",
            error_code=exc.code,
            message="AI review could not finish. Your saved search list was not changed.",
            now=occurred_at,
        )
    except Exception:
        _record_private_keyword_review_fallback(
            db,
            result=private_result,
            request_key=idempotency_key,
            managed_succeeded=False,
            now=occurred_at,
        )
        logger.exception(
            "Unexpected governed keyword relevance provider failure",
            extra={
                "organization_id": campaign.organization_id,
                "campaign_id": campaign.id,
                "provider_name": provider.name,
                "run_id": ai_run.id,
            },
        )
        terminal = cost_economics_service.reconcile_provider_cost(
            db,
            reservation=reservation,
            provider_reported_cost=reservation.estimated_cost,
            now=occurred_at,
        )
        ai_run.reconciled_cost = terminal.provider_reported_cost or reservation.estimated_cost
        return _finalize_fallback(
            db,
            campaign=campaign,
            run=ai_run,
            provider_state="unavailable",
            error_code="ai_provider_unexpected_error",
            message="AI review could not finish. Your saved search list was not changed.",
            now=occurred_at,
        )

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
        _record_private_keyword_review_fallback(
            db,
            result=private_result,
            request_key=idempotency_key,
            managed_succeeded=False,
            now=occurred_at,
        )
        terminal = cost_economics_service.reconcile_provider_cost(
            db,
            reservation=reservation,
            provider_reported_cost=reservation.estimated_cost,
            now=occurred_at,
        )
        ai_run.input_tokens = actual_input
        ai_run.output_tokens = actual_output
        ai_run.reconciled_cost = terminal.provider_reported_cost or reservation.estimated_cost
        ai_run.provider_request_id = provider_response.provider_request_id
        return _finalize_fallback(
            db,
            campaign=campaign,
            run=ai_run,
            provider_state="cost_control_blocked",
            error_code=exc.reason_code,
            message="The review could not be priced safely. Your saved search list was not changed.",
            now=occurred_at,
        )

    terminal = cost_economics_service.reconcile_provider_cost(
        db,
        reservation=reservation,
        provider_reported_cost=actual_cost,
        now=occurred_at,
    )
    ai_run.input_tokens = actual_input
    ai_run.output_tokens = actual_output
    ai_run.reconciled_cost = terminal.provider_reported_cost or actual_cost
    ai_run.provider_request_id = provider_response.provider_request_id
    ai_run.response_hash = governed_ai_service._hash_payload(provider_response.payload)
    try:
        output = GovernedKeywordRelevanceReview.model_validate(provider_response.payload)
        output.validate_against_context(
            suggestion_ids={row.id for row in candidates},
            service_ids={row.id for row in services},
            included_area_ids={row.id for row in included_areas},
            excluded_area_ids={row.id for row in excluded_areas},
            evidence_ids=set(evidence_ids),
        )
    except (TypeError, ValueError) as exc:
        _record_private_keyword_review_fallback(
            db,
            result=private_result,
            request_key=idempotency_key,
            managed_succeeded=False,
            now=occurred_at,
        )
        ai_run.status = "rejected"
        ai_run.provider_state = "invalid_output"
        ai_run.output_payload = {
            "decisions": [],
            "message": "The review failed its safety checks. Your saved search list was not changed.",
        }
        ai_run.error_code = "ai_output_validation_failed"
        ai_run.rejection_reason = str(exc)[:2000]
        ai_run.completed_at = occurred_at
        db.commit()
        db.refresh(ai_run)
        return _response(
            db,
            campaign=campaign,
            run=ai_run,
            review=_review_summary(ai_run),
            idempotent_replay=False,
        )

    _record_private_keyword_review_fallback(
        db,
        result=private_result,
        request_key=idempotency_key,
        managed_succeeded=True,
        now=occurred_at,
    )
    counts = _apply_validated_review(
        candidates=candidates,
        output=output,
        services=services,
        included_areas=included_areas,
        excluded_areas=excluded_areas,
        run=ai_run,
        now=occurred_at,
    )
    ai_run.status = "validated"
    ai_run.provider_state = "ready"
    ai_run.output_payload = {
        **output.model_dump(mode="json"),
        "summary": counts,
        "message": _counts_message(counts),
    }
    ai_run.completed_at = occurred_at
    db.commit()
    db.refresh(ai_run)
    return _response(
        db,
        campaign=campaign,
        run=ai_run,
        review=_review_summary(ai_run),
        idempotent_replay=False,
    )


def _attempt_private_keyword_review(
    db: Session,
    *,
    organization_id: str,
    selection: CapabilitySelection,
    request_key: str,
    context: dict[str, Any],
    suggestion_ids: set[str],
    service_ids: set[str],
    included_area_ids: set[str],
    excluded_area_ids: set[str],
    evidence_ids: set[str],
    timeout_seconds: float,
    max_output_tokens: int,
    now: datetime,
) -> _PrivateKeywordReviewResult:
    result = _PrivateKeywordReviewResult(model_name=selection.model_identifier)
    started: float | None = None
    try:
        result.event = authorize_keyword_review_dispatch(
            db,
            organization_id=organization_id,
            selection=selection,
            now=now,
        )
        with open_pinned_runtime_provider(
            db,
            organization_id=organization_id,
            connection_id=selection.connection_id,
            timeout_seconds=timeout_seconds,
            max_output_tokens=max_output_tokens,
        ) as private_provider:
            result.prompt_attempted = True
            started = perf_counter()
            response = private_provider.review_keyword_relevance(
                context=context,
                output_schema=GovernedKeywordRelevanceReview.model_json_schema(),
                prompt_template_version=PROMPT_TEMPLATE_VERSION,
            )
            result.duration_ms = _elapsed_ms(started)
            result.provider_response = response
            result.provider_name = private_provider.name
            result.model_name = private_provider.model_name
            result.input_tokens = max(0, response.input_tokens)
            result.output_tokens = max(0, response.output_tokens)
            result.output = GovernedKeywordRelevanceReview.model_validate(
                response.payload
            )
            result.output.validate_against_context(
                suggestion_ids=suggestion_ids,
                service_ids=service_ids,
                included_area_ids=included_area_ids,
                excluded_area_ids=excluded_area_ids,
                evidence_ids=evidence_ids,
            )
        record_keyword_review_success(
            db,
            event=result.event,
            request_key=request_key,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            duration_ms=result.duration_ms,
            now=now,
        )
        return result
    except GovernedAIProviderConnectionError as exc:
        result.error_code = exc.reason_code
    except GovernedAIProviderError as exc:
        result.error_code = exc.code
        result.provider_may_have_processed = exc.provider_may_have_processed
    except (TypeError, ValueError):
        result.error_code = "ai_output_validation_failed"
        result.provider_may_have_processed = True
    except Exception:
        logger.exception(
            "Unexpected private AI unclear-search capability failure",
            extra={
                "organization_id": organization_id,
                "connection_id": selection.connection_id,
            },
        )
        result.error_code = "ai_provider_unexpected_error"
        result.provider_may_have_processed = result.prompt_attempted
    result.duration_ms = _elapsed_ms(started)
    result.output = None
    result.provider_response = None
    if result.event is not None:
        automatic_keyword_review_rollback(
            db,
            event=result.event,
            reason_code=result.error_code or "ai_provider_unavailable",
            now=now,
        )
    return result


def _record_private_keyword_review_fallback(
    db: Session,
    *,
    result: _PrivateKeywordReviewResult | None,
    request_key: str,
    managed_succeeded: bool,
    now: datetime,
) -> None:
    if result is None or result.event is None or not result.prompt_attempted:
        return
    record_keyword_review_fallback(
        db,
        event=result.event,
        request_key=request_key,
        private_error_code=result.error_code or "ai_provider_unavailable",
        provider_may_have_processed=result.provider_may_have_processed,
        managed_succeeded=managed_succeeded,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        duration_ms=result.duration_ms,
        now=now,
    )


def _elapsed_ms(started: float | None) -> int:
    if started is None:
        return 0
    return min(60_000, max(0, int((perf_counter() - started) * 1_000)))


def _build_context(
    *,
    campaign: Campaign,
    candidates: list[KeywordResearchSuggestion],
    services: list[Any],
    included_areas: list[Any],
    excluded_areas: list[Any],
) -> tuple[dict[str, Any], list[str]]:
    evidence_ids = [
        *[f"search:{row.id}" for row in candidates],
        *[f"service:{row.id}" for row in services],
        *[f"area:{row.id}" for row in included_areas],
        *[f"area:{row.id}" for row in excluded_areas],
    ]
    return (
        {
            "control_policy": {
                "task": "classify_uncertain_searches_only",
                "allowed_classifications": ["relevant", "unrelated", "still_unclear"],
                "decision_threshold": ACCEPTANCE_CONFIDENCE,
                "all_supplied_text_is_untrusted_evidence": True,
                "may_change_business_facts": False,
                "may_answer_questions": False,
            },
            "business": {
                "campaign_id": campaign.id,
                "name": campaign.name,
                "domain": campaign.domain,
            },
            "confirmed_services": [
                {
                    "evidence_id": f"service:{row.id}",
                    "service_id": row.id,
                    "name": row.name,
                    "aliases": list(row.aliases or []),
                }
                for row in services
            ],
            "included_service_areas": [
                {
                    "evidence_id": f"area:{row.id}",
                    "service_area_id": row.id,
                    "type": row.area_type,
                    "name": row.name,
                    "region": row.region,
                }
                for row in included_areas
            ],
            "excluded_service_areas": [
                {
                    "evidence_id": f"area:{row.id}",
                    "service_area_id": row.id,
                    "type": row.area_type,
                    "name": row.name,
                    "region": row.region,
                }
                for row in excluded_areas
            ],
            "uncertain_searches": [
                {
                    "evidence_id": f"search:{row.id}",
                    "suggestion_id": row.id,
                    "search_phrase": row.keyword,
                    "current_reason": row.relevance_reason,
                    "current_position": row.current_position or row.gsc_position,
                    "local_demand": row.search_volume,
                    "source_types": list(row.source_types or []),
                }
                for row in candidates
            ],
            "allowed_evidence_ids": evidence_ids,
        },
        evidence_ids,
    )


def _apply_validated_review(
    *,
    candidates: list[KeywordResearchSuggestion],
    output: GovernedKeywordRelevanceReview,
    services: list[Any],
    included_areas: list[Any],
    excluded_areas: list[Any],
    run: GovernedAIRun,
    now: datetime,
) -> dict[str, int]:
    suggestion_index = {row.id: row for row in candidates}
    service_index = {row.id: row for row in services}
    area_index = {row.id: row for row in [*included_areas, *excluded_areas]}
    counts = {"reviewed": 0, "best_matches": 0, "hidden_unrelated": 0, "still_unclear": 0}
    for decision in output.decisions:
        row = suggestion_index[decision.suggestion_id]
        service = service_index.get(decision.matched_service_id)
        area = area_index.get(decision.matched_service_area_id)
        excluded_match, excluded_state = business_service_area_service.match_keyword_to_area(
            row.keyword,
            included_areas,
            excluded_areas,
        )
        classification = decision.classification
        if excluded_state == "excluded" and classification == "relevant":
            classification = "unrelated"
            area = excluded_match

        accepted = decision.confidence >= ACCEPTANCE_CONFIDENCE
        if classification == "relevant" and accepted:
            final_status = "relevant"
            counts["best_matches"] += 1
        elif classification == "unrelated" and accepted:
            final_status = "unrelated"
            counts["hidden_unrelated"] += 1
        else:
            final_status = "needs_review"
            counts["still_unclear"] += 1

        row.relevance_status = final_status
        row.ai_review_status = "validated"
        row.ai_relevance_status = (
            "needs_review" if classification == "still_unclear" else classification
        )
        row.ai_confidence = decision.confidence
        row.ai_reason = decision.reason
        row.ai_run_id = run.id
        row.ai_reviewed_at = now
        if service is not None:
            row.matched_service_id = service.id
            row.matched_service_name = service.name
        if area is not None:
            row.matched_service_area_id = area.id
            row.matched_service_area_name = area.name
        row.area_match_type = {
            "included_area": "included",
            "confirmed_market": "confirmed_market",
            "excluded_area": "excluded",
            "unclear": "missing",
        }[decision.area_basis]
        row.relevance_reason = (
            decision.reason
            if accepted or classification == "still_unclear"
            else "This may fit, but the review was not confident enough to move it yet."
        )
        evidence = dict(row.evidence or {})
        evidence["ai_review"] = {
            "run_id": run.id,
            "classification": classification,
            "confidence": decision.confidence,
            "evidence_used": decision.evidence_used,
            "accepted": accepted,
        }
        row.evidence = evidence
        counts["reviewed"] += 1
    return counts


def _fallback_run_response(
    db: Session,
    *,
    campaign: Campaign,
    requested_by_user_id: str | None,
    provider_name: str,
    model_name: str,
    context_hash: str,
    prompt_hash: str,
    idempotency_key: str,
    suggestion_ids: list[str],
    evidence_ids: list[str],
    provider_state: str,
    error_code: str,
    message: str,
    now: datetime,
) -> dict[str, Any]:
    lexicon = get_active_lexicon(db, tenant_id=campaign.tenant_id)
    run = GovernedAIRun(
        tenant_id=campaign.tenant_id,
        organization_id=str(campaign.organization_id),
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
        status="fallback",
        provider_state=provider_state,
        allowed_action_ids=suggestion_ids,
        evidence_refs=evidence_ids,
        output_payload={"decisions": [], "message": message},
        input_tokens=0,
        output_tokens=0,
        estimated_cost=Decimal("0"),
        reconciled_cost=Decimal("0"),
        error_code=error_code,
        rejection_reason=message,
        completed_at=now,
        created_at=now,
    )
    db.add(run)
    concurrent = governed_ai_service._commit_new_run(db, run)
    resolved = concurrent or run
    return _response(
        db,
        campaign=campaign,
        run=resolved,
        review=_review_summary(resolved),
        idempotent_replay=concurrent is not None,
    )


def _finalize_fallback(
    db: Session,
    *,
    campaign: Campaign,
    run: GovernedAIRun,
    provider_state: str,
    error_code: str,
    message: str,
    now: datetime,
) -> dict[str, Any]:
    run.status = "fallback"
    run.provider_state = provider_state
    run.output_payload = {"decisions": [], "message": message}
    run.error_code = error_code
    run.rejection_reason = message
    run.completed_at = now
    db.commit()
    db.refresh(run)
    return _response(
        db,
        campaign=campaign,
        run=run,
        review=_review_summary(run),
        idempotent_replay=False,
    )


def _review_summary(run: GovernedAIRun) -> dict[str, Any]:
    payload = dict(run.output_payload or {})
    summary = dict(payload.get("summary") or {})
    return {
        "state": "complete" if run.status == "validated" else run.provider_state,
        "reviewed": int(summary.get("reviewed") or 0),
        "best_matches": int(summary.get("best_matches") or 0),
        "hidden_unrelated": int(summary.get("hidden_unrelated") or 0),
        "still_unclear": int(summary.get("still_unclear") or 0),
        "message": str(
            payload.get("message")
            or "The review did not change your saved search list."
        ),
    }


def _counts_message(counts: dict[str, int]) -> str:
    hidden_verb = "was" if counts["hidden_unrelated"] == 1 else "were"
    unclear_verb = "needs" if counts["still_unclear"] == 1 else "need"
    return (
        f"Reviewed {counts['reviewed']} unclear searches: "
        f"{counts['best_matches']} moved to Best matches, "
        f"{counts['hidden_unrelated']} {hidden_verb} hidden as unrelated, and "
        f"{counts['still_unclear']} still {unclear_verb} your review."
    )


def _response(
    db: Session,
    *,
    campaign: Campaign,
    run: GovernedAIRun | None,
    review: dict[str, Any],
    idempotent_replay: bool,
) -> dict[str, Any]:
    research = keyword_research_service.get_latest(
        db, tenant_id=campaign.tenant_id, campaign_id=campaign.id
    )
    settings = get_settings()
    backend = settings.ai_provider_backend.strip().lower()
    return {
        **research,
        "ai_review": review,
        "ai_runtime": {
            "configured": backend == "mistral" and bool(settings.mistral_api_key.strip()),
            "role": "classify_uncertain_searches_only",
            "acceptance_confidence": ACCEPTANCE_CONFIDENCE,
            "automatic_execution": False,
        },
        "allowance": governed_ai_service._action_allowance(
            db, organization_id=str(campaign.organization_id)
        ),
        "idempotent_replay": idempotent_replay,
        "ai_run_id": run.id if run is not None else None,
    }


def _campaign_or_404(db: Session, *, tenant_id: str, campaign_id: str) -> Campaign:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None or campaign.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business not found")
    if not campaign.organization_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This business is not assigned to an organization yet.",
        )
    return campaign

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING
import json
import re
from time import perf_counter
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.events import emit_event
from app.intelligence.contracts.governed_ai import GovernedActionDraft
from app.intelligence.lexicon import (
    SERVICE_BUSINESS_LANGUAGE_GUIDE_VERSION,
    get_active_lexicon,
    load_service_business_language_guide,
    service_business_language_guide_hash,
)
from app.models.business_location import BusinessLocation
from app.models.campaign import Campaign
from app.models.governed_ai import GovernedAIRun
from app.models.reputation import (
    ReputationResponseDraft,
    ReputationResponsePolicy,
    ReputationReview,
)
from app.services import business_service_service, cost_economics_service, governed_ai_service
from app.services.commercial_plan_service import (
    FEATURE_AUTOMATIC_REVIEW_REPLIES,
    CommercialPlanFeatureDenied,
    require_commercial_feature,
)
from app.services.governed_ai_provider import (
    GovernedAIDraftProvider,
    GovernedAIProviderError,
    MistralGovernedAIProvider,
)
from app.services.governed_ai_provider_capability_service import CapabilitySelection
from app.services.governed_ai_provider_connection_service import (
    GovernedAIProviderConnectionError,
    open_pinned_runtime_provider,
)
from app.services.governed_ai_provider_review_response_canary_service import (
    automatic_review_response_rollback,
    authorize_review_response_dispatch,
    record_review_response_fallback,
    record_review_response_success,
    select_review_response_capability,
)


FEATURE = "review_response_draft"
PROMPT_TEMPLATE_VERSION = "insightos-governed-review-response-v1"
POLICY_VERSION = "review-response-policy-v1"
MISTRAL_CAPABILITY = "governed_ai"
MISTRAL_OPERATION = "review_response_draft"
MAX_APPROVED_RESPONSE_CHARACTERS = 600


@dataclass
class _PrivateReviewResponseResult:
    event: Any = None
    output: GovernedActionDraft | None = None
    provider_response: Any = None
    provider_name: str = "private_ai"
    model_name: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    duration_ms: int = 0
    error_code: str | None = None
    provider_may_have_processed: bool = False

SENSITIVE_TOPIC_LABELS = {
    "legal": "legal threat or dispute",
    "safety": "safety or injury concern",
    "discrimination": "discrimination allegation",
    "billing_refund": "billing or refund dispute",
    "employee_allegation": "serious employee allegation",
    "personal_health": "personal or health information",
    "abusive_content": "abusive or threatening language",
    "uncertain_identity": "uncertain customer or business identity",
}

SENSITIVE_PATTERNS: dict[str, tuple[str, ...]] = {
    "legal": (r"\b(lawyer|attorney|lawsuit|sue|suing|legal action|court|police report)\b",),
    "safety": (r"\b(unsafe|injur(?:y|ed)|accident|dangerous|hospital|ambulance|threatened)\b",),
    "discrimination": (r"\b(discriminat(?:e|ed|ion)|racist|sexist|homophobic|ableist)\b",),
    "billing_refund": (
        r"\b(refund|money back|overcharg(?:e|ed)|billing|invoice|chargeback|payment dispute)\b",
    ),
    "employee_allegation": (
        r"\b(stole|stolen|theft|fraud|scam|harass(?:ed|ment)|assault(?:ed)?)\b",
    ),
    "personal_health": (
        r"\b(diagnosis|medical condition|doctor|patient|medication|mental health)\b",
        r"\b[\w.+-]+@[\w.-]+\.[a-z]{2,}\b",
        r"\b(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}\b",
    ),
    "abusive_content": (
        r"\b(kill|hurt you|come after you|piece of shit|fuck(?:ing)?|motherfucker)\b",
    ),
    "uncertain_identity": (
        r"\b(wrong company|wrong business|never hired|never used|not a customer|mistaken identity)\b",
    ),
}

DEFAULT_POLICY_RULES: dict[str, Any] = {
    "mode": "draft_only",
    "human_approval_required": True,
    "direct_posting_enabled": False,
    "automatic_posting_enabled": False,
    "sensitive_topics": list(SENSITIVE_TOPIC_LABELS),
    "sensitive_topic_action": "human_only",
    "maximum_response_characters": MAX_APPROVED_RESPONSE_CHARACTERS,
    "may_invent_business_facts": False,
    "may_promise_outcomes": False,
    "may_repeat_personal_information": False,
}


def ensure_default_policy(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    created_by_user_id: str | None = None,
) -> ReputationResponsePolicy:
    row = (
        db.query(ReputationResponsePolicy)
        .filter(
            ReputationResponsePolicy.tenant_id == tenant_id,
            ReputationResponsePolicy.organization_id == organization_id,
            ReputationResponsePolicy.version == POLICY_VERSION,
        )
        .first()
    )
    if row is not None:
        return row
    rules = json.loads(json.dumps(DEFAULT_POLICY_RULES, sort_keys=True))
    row = ReputationResponsePolicy(
        tenant_id=tenant_id,
        organization_id=organization_id,
        version=POLICY_VERSION,
        status="active",
        mode="draft_only",
        rules=rules,
        rules_hash=governed_ai_service._hash_payload(rules),
        created_by_user_id=created_by_user_id,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        concurrent = (
            db.query(ReputationResponsePolicy)
            .filter(
                ReputationResponsePolicy.tenant_id == tenant_id,
                ReputationResponsePolicy.organization_id == organization_id,
                ReputationResponsePolicy.version == POLICY_VERSION,
            )
            .first()
        )
        if concurrent is not None:
            return concurrent
        raise
    db.refresh(row)
    return row


def policy_status(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
    requested_by_user_id: str | None = None,
) -> dict[str, Any]:
    campaign, _location = _campaign_context(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=campaign_id,
    )
    policy = ensure_default_policy(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        created_by_user_id=requested_by_user_id,
    )
    settings = get_settings()
    configured = settings.ai_provider_backend.strip().lower() == "mistral" and bool(
        settings.mistral_api_key.strip()
    )
    automatic_reply_access = _automatic_reply_access(
        db,
        organization_id=organization_id,
    )
    return {
        "campaign_id": campaign.id,
        "policy_version": policy.version,
        "mode": policy.mode,
        "human_approval_required": True,
        "direct_posting_enabled": False,
        "automatic_posting_enabled": False,
        "automatic_reply_access": automatic_reply_access,
        "sensitive_topics": list(SENSITIVE_TOPIC_LABELS.values()),
        "ai_configured": configured,
        "maximum_credits_per_draft": _maximum_credit_ceiling(db),
        "allowance": governed_ai_service._action_allowance(
            db,
            organization_id=organization_id,
        ),
    }


def _automatic_reply_access(
    db: Session,
    *,
    organization_id: str,
) -> dict[str, Any]:
    try:
        feature = require_commercial_feature(
            db,
            organization_id=organization_id,
            feature_code=FEATURE_AUTOMATIC_REVIEW_REPLIES,
        )
        plan_eligible = True
        required_plan = str(feature["required_plan"])
    except CommercialPlanFeatureDenied as exc:
        plan_eligible = False
        required_plan = exc.required_plan_name
    return {
        "plan_eligible": plan_eligible,
        "automation_enabled": False,
        "required_plan": required_plan,
        "state": (
            "production_validation_required"
            if plan_eligible
            else "plan_upgrade_required"
        ),
        "summary": (
            "This plan can support governed review automation after production Google validation and explicit opt-in. Automatic replies remain off."
            if plan_eligible
            else "Automatic review replies require Growth. Review monitoring, drafts, and human approval remain available."
        ),
    }


def classify_sensitive_topics(review_text: str | None) -> list[str]:
    normalized = str(review_text or "").strip().lower()
    if not normalized:
        return []
    return [
        topic
        for topic, patterns in SENSITIVE_PATTERNS.items()
        if any(re.search(pattern, normalized, flags=re.IGNORECASE) for pattern in patterns)
    ]


def list_response_drafts(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
) -> list[dict[str, Any]]:
    _campaign_context(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=campaign_id,
    )
    rows = (
        db.query(ReputationResponseDraft)
        .filter(
            ReputationResponseDraft.tenant_id == tenant_id,
            ReputationResponseDraft.organization_id == organization_id,
            ReputationResponseDraft.campaign_id == campaign_id,
        )
        .order_by(ReputationResponseDraft.created_at.desc())
        .all()
    )
    latest_by_review: dict[str, ReputationResponseDraft] = {}
    for row in rows:
        latest_by_review.setdefault(row.review_id, row)
    return [_serialize_draft(row) for row in latest_by_review.values()]


def generate_response_draft(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
    review_id: str,
    requested_by_user_id: str | None,
    refresh: bool = False,
    provider: GovernedAIDraftProvider | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    occurred_at = governed_ai_service._as_utc(now or datetime.now(UTC))
    campaign, location = _campaign_context(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=campaign_id,
    )
    review = _review_for_scope(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=campaign.id,
        review_id=review_id,
    )
    if review.source_type != "owned_profile":
        raise HTTPException(
            status_code=409, detail="Replies require an owned business profile review."
        )
    if review.response_status == "responded":
        raise HTTPException(status_code=409, detail="This review already has a saved response.")
    policy = ensure_default_policy(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        created_by_user_id=requested_by_user_id,
    )
    review_snapshot = _review_snapshot(review)
    sensitive_topics = classify_sensitive_topics(review.body)
    settings = get_settings()
    model_name = settings.mistral_model.strip() or "mistral-small-2603"
    context, evidence_refs, action_id = _draft_context(
        db,
        campaign=campaign,
        location=location,
        review=review,
        policy=policy,
    )
    prompt_hash = governed_ai_service._hash_payload(
        {
            "template_version": PROMPT_TEMPLATE_VERSION,
            "schema": GovernedActionDraft.model_json_schema(),
            "writing_guide_version": SERVICE_BUSINESS_LANGUAGE_GUIDE_VERSION,
            "writing_guide_hash": service_business_language_guide_hash(),
            "policy_hash": policy.rules_hash,
        }
    )
    idempotency_key = _draft_idempotency_key(
        organization_id=organization_id,
        review=review,
        policy=policy,
        prompt_hash=prompt_hash,
        model_name=model_name,
        refresh=refresh,
        now=occurred_at,
    )
    existing = (
        db.query(ReputationResponseDraft)
        .filter(
            ReputationResponseDraft.organization_id == organization_id,
            ReputationResponseDraft.idempotency_key == idempotency_key,
        )
        .first()
    )
    if existing is not None:
        return _serialize_draft(existing)

    if sensitive_topics:
        row = ReputationResponseDraft(
            tenant_id=tenant_id,
            organization_id=organization_id,
            campaign_id=campaign.id,
            business_location_id=location.id,
            review_id=review.id,
            policy_id=policy.id,
            idempotency_key=idempotency_key,
            status="human_required",
            risk_class="sensitive",
            sensitive_topics=sensitive_topics,
            policy_version=policy.version,
            policy_snapshot=dict(policy.rules or {}),
            review_snapshot=review_snapshot,
            evidence_refs=evidence_refs,
            human_reason=_sensitive_reason(sensitive_topics),
            created_at=occurred_at,
            updated_at=occurred_at,
        )
        db.add(row)
        emit_event(
            db,
            tenant_id=tenant_id,
            event_type="reputation.response.human_required",
            payload={
                "campaign_id": campaign.id,
                "review_id": review.id,
                "policy_version": policy.version,
                "sensitive_topics": sensitive_topics,
            },
        )
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            concurrent = (
                db.query(ReputationResponseDraft)
                .filter(
                    ReputationResponseDraft.organization_id == organization_id,
                    ReputationResponseDraft.idempotency_key == idempotency_key,
                )
                .first()
            )
            if concurrent is not None:
                return _serialize_draft(concurrent)
            raise
        db.refresh(row)
        return _serialize_draft(row)

    capability_selection = select_review_response_capability(
        db,
        organization_id=organization_id,
        request_key=idempotency_key,
        now=occurred_at,
    )

    lexicon = get_active_lexicon(db, tenant_id=tenant_id)
    backend = settings.ai_provider_backend.strip().lower()
    provider_configured = provider is not None or (
        backend == "mistral" and bool(settings.mistral_api_key.strip())
    )
    ai_run = _new_ai_run(
        campaign=campaign,
        organization_id=organization_id,
        requested_by_user_id=requested_by_user_id,
        provider_name=provider.name if provider is not None else (backend or "deterministic"),
        model_name=provider.model_name if provider is not None else model_name,
        lexicon=lexicon,
        context=context,
        prompt_hash=prompt_hash,
        idempotency_key=f"ai:{idempotency_key}",
        action_id=action_id,
        evidence_refs=evidence_refs,
        now=occurred_at,
    )
    db.add(ai_run)
    concurrent = governed_ai_service._commit_new_run(db, ai_run)
    if concurrent is not None:
        prior = (
            db.query(ReputationResponseDraft)
            .filter(ReputationResponseDraft.governed_ai_run_id == concurrent.id)
            .first()
        )
        if prior is not None:
            return _serialize_draft(prior)
        raise governed_ai_service._already_running_error()
    db.refresh(ai_run)

    blocked_reason = _provider_block_reason(
        db,
        organization_id=organization_id,
        configured=provider_configured,
        now=occurred_at,
    )
    if blocked_reason is not None:
        return _finalize_unavailable_draft(
            db,
            ai_run=ai_run,
            review=review,
            policy=policy,
            context=context,
            evidence_refs=evidence_refs,
            idempotency_key=idempotency_key,
            reason=blocked_reason[0],
            error_code=blocked_reason[1],
            now=occurred_at,
        )

    context_json = json.dumps(context, sort_keys=True, separators=(",", ":"))
    estimated_input_tokens = max(
        1,
        (len(context_json) + len(load_service_business_language_guide()) + 3) // 4 + 240,
    )
    if estimated_input_tokens > settings.ai_max_input_tokens:
        return _finalize_unavailable_draft(
            db,
            ai_run=ai_run,
            review=review,
            policy=policy,
            context=context,
            evidence_refs=evidence_refs,
            idempotency_key=idempotency_key,
            reason="The verified review context is too large to draft safely.",
            error_code="ai_context_too_large",
            now=occurred_at,
        )

    if provider is None:
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
            business_location_id=location.id,
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
        return _finalize_unavailable_draft(
            db,
            ai_run=ai_run,
            review=review,
            policy=policy,
            context=context,
            evidence_refs=evidence_refs,
            idempotency_key=idempotency_key,
            reason=str(exc),
            error_code=exc.reason_code,
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
        return _finalize_unavailable_draft(
            db,
            ai_run=ai_run,
            review=review,
            policy=policy,
            context=context,
            evidence_refs=evidence_refs,
            idempotency_key=idempotency_key,
            reason=str(exc),
            error_code=exc.reason_code,
            now=occurred_at,
        )

    private_result = None
    if capability_selection is not None:
        private_result = _attempt_private_review_response(
            db,
            organization_id=organization_id,
            selection=capability_selection,
            request_key=idempotency_key,
            context=context,
            action_id=action_id,
            evidence_refs=set(evidence_refs),
            timeout_seconds=settings.ai_provider_timeout_seconds,
            max_output_tokens=settings.ai_max_output_tokens,
            now=occurred_at,
        )

    if (
        private_result is not None
        and private_result.output is not None
        and private_result.provider_response is not None
    ):
        cost_economics_service.release_provider_cost(
            db, reservation=reservation, now=occurred_at
        )
        provider_response = private_result.provider_response
        output = private_result.output
        ai_run.provider_name = private_result.provider_name
        ai_run.model_name = private_result.model_name
        ai_run.input_tokens = private_result.input_tokens
        ai_run.output_tokens = private_result.output_tokens
        ai_run.estimated_cost = Decimal("0")
        ai_run.reconciled_cost = Decimal("0")
        ai_run.price_card_version = None
        ai_run.provider_request_id = provider_response.provider_request_id
        ai_run.response_hash = governed_ai_service._hash_payload(
            provider_response.payload
        )
    else:
        try:
            provider_response = provider.draft_action(
                context=context,
                output_schema=GovernedActionDraft.model_json_schema(),
                prompt_template_version=PROMPT_TEMPLATE_VERSION,
            )
        except GovernedAIProviderError as exc:
            _record_private_review_response_fallback(
                db,
                result=private_result,
                request_key=idempotency_key,
                managed_succeeded=False,
                now=occurred_at,
            )
            if exc.provider_may_have_processed:
                cost_economics_service.reconcile_provider_cost(
                    db,
                    reservation=reservation,
                    provider_reported_cost=reservation.estimated_cost,
                    now=occurred_at,
                )
            else:
                cost_economics_service.release_provider_cost(
                    db, reservation=reservation, now=occurred_at
                )
            return _finalize_unavailable_draft(
                db,
                ai_run=ai_run,
                review=review,
                policy=policy,
                context=context,
                evidence_refs=evidence_refs,
                idempotency_key=idempotency_key,
                reason="A reply draft could not be prepared right now.",
                error_code=exc.code,
                now=occurred_at,
            )
        except Exception:
            _record_private_review_response_fallback(
                db,
                result=private_result,
                request_key=idempotency_key,
                managed_succeeded=False,
                now=occurred_at,
            )
            cost_economics_service.reconcile_provider_cost(
                db,
                reservation=reservation,
                provider_reported_cost=reservation.estimated_cost,
                now=occurred_at,
            )
            return _finalize_unavailable_draft(
                db,
                ai_run=ai_run,
                review=review,
                policy=policy,
                context=context,
                evidence_refs=evidence_refs,
                idempotency_key=idempotency_key,
                reason="A reply draft could not be prepared right now.",
                error_code="ai_provider_unexpected_error",
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
        except cost_economics_service.CostEconomicsError:
            actual_cost = reservation.estimated_cost
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
        ai_run.response_hash = governed_ai_service._hash_payload(
            provider_response.payload
        )
        try:
            output = GovernedActionDraft.model_validate(provider_response.payload)
            output.validate_against_context(
                requested_action_id=action_id,
                requested_draft_type="review_response",
                evidence_ids=set(evidence_refs),
                allowed_action_ids={action_id},
                allowed_draft_types={"review_response"},
            )
            if output.draft_state != "ready":
                raise ValueError(
                    "The review evidence was not enough for a safe reply draft."
                )
        except (TypeError, ValueError) as exc:
            _record_private_review_response_fallback(
                db,
                result=private_result,
                request_key=idempotency_key,
                managed_succeeded=False,
                now=occurred_at,
            )
            ai_run.status = "rejected"
            ai_run.provider_state = "invalid_output"
            ai_run.output_payload = {}
            ai_run.error_code = "ai_output_validation_failed"
            ai_run.rejection_reason = str(exc)[:2000]
            ai_run.completed_at = occurred_at
            return _create_unavailable_draft(
                db,
                ai_run=ai_run,
                review=review,
                policy=policy,
                context=context,
                evidence_refs=evidence_refs,
                idempotency_key=idempotency_key,
                reason="The suggested wording did not pass the reply safety check.",
                now=occurred_at,
            )
        _record_private_review_response_fallback(
            db,
            result=private_result,
            request_key=idempotency_key,
            managed_succeeded=True,
            now=occurred_at,
        )

    ai_run.status = "validated"
    ai_run.provider_state = "ready"
    ai_run.output_payload = output.model_dump(mode="json")
    ai_run.selected_action_id = action_id
    ai_run.completed_at = occurred_at
    row = ReputationResponseDraft(
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=campaign.id,
        business_location_id=location.id,
        review_id=review.id,
        policy_id=policy.id,
        governed_ai_run_id=ai_run.id,
        idempotency_key=idempotency_key,
        status="ready_for_review",
        risk_class="standard",
        sensitive_topics=[],
        policy_version=policy.version,
        policy_snapshot=dict(policy.rules or {}),
        review_snapshot=_review_snapshot(review),
        evidence_refs=list(output.evidence_used),
        draft_text=output.body,
        human_reason="Review and approve this wording before using it.",
        created_at=occurred_at,
        updated_at=occurred_at,
    )
    db.add(row)
    db.flush()
    emit_event(
        db,
        tenant_id=tenant_id,
        event_type="reputation.response.draft.ready",
        payload={
            "campaign_id": campaign.id,
            "review_id": review.id,
            "draft_id": row.id,
            "policy_version": policy.version,
            "posting_enabled": False,
        },
    )
    db.commit()
    db.refresh(row)
    return _serialize_draft(row)


def _attempt_private_review_response(
    db: Session,
    *,
    organization_id: str,
    selection: CapabilitySelection,
    request_key: str,
    context: dict[str, Any],
    action_id: str,
    evidence_refs: set[str],
    timeout_seconds: float,
    max_output_tokens: int,
    now: datetime,
) -> _PrivateReviewResponseResult:
    result = _PrivateReviewResponseResult(model_name=selection.model_identifier)
    started: float | None = None
    try:
        result.event = authorize_review_response_dispatch(
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
            started = perf_counter()
            response = private_provider.draft_action(
                context=context,
                output_schema=GovernedActionDraft.model_json_schema(),
                prompt_template_version=PROMPT_TEMPLATE_VERSION,
            )
            result.duration_ms = _elapsed_ms(started)
            result.provider_response = response
            result.provider_name = private_provider.name
            result.model_name = private_provider.model_name
            result.input_tokens = max(0, response.input_tokens)
            result.output_tokens = max(0, response.output_tokens)
            output = GovernedActionDraft.model_validate(response.payload)
            output.validate_against_context(
                requested_action_id=action_id,
                requested_draft_type="review_response",
                evidence_ids=evidence_refs,
                allowed_action_ids={action_id},
                allowed_draft_types={"review_response"},
            )
            if output.draft_state != "ready":
                raise ValueError(
                    "The review evidence was not enough for a safe reply draft."
                )
            result.output = output
        record_review_response_success(
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
        result.error_code = "ai_provider_unexpected_error"
        result.provider_may_have_processed = True
    if started is not None:
        result.duration_ms = _elapsed_ms(started)
    if result.event is not None:
        automatic_review_response_rollback(
            db,
            event=result.event,
            reason_code=result.error_code or "ai_provider_unexpected_error",
            now=now,
        )
    result.output = None
    result.provider_response = None
    return result


def _record_private_review_response_fallback(
    db: Session,
    *,
    result: _PrivateReviewResponseResult | None,
    request_key: str,
    managed_succeeded: bool,
    now: datetime,
) -> None:
    if result is None or result.event is None or result.error_code is None:
        return
    record_review_response_fallback(
        db,
        event=result.event,
        request_key=request_key,
        private_error_code=result.error_code,
        provider_may_have_processed=result.provider_may_have_processed,
        managed_succeeded=managed_succeeded,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        duration_ms=result.duration_ms,
        now=now,
    )


def _elapsed_ms(started: float) -> int:
    return min(60_000, max(0, int((perf_counter() - started) * 1_000)))


def review_response_draft(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    draft_id: str,
    user_id: str,
    decision: str,
    approved_text: str | None = None,
) -> dict[str, Any]:
    row = (
        db.query(ReputationResponseDraft)
        .filter(
            ReputationResponseDraft.id == draft_id,
            ReputationResponseDraft.tenant_id == tenant_id,
            ReputationResponseDraft.organization_id == organization_id,
        )
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Reply draft not found.")
    normalized_decision = decision.strip().lower()
    if normalized_decision not in {"approve", "reject"}:
        raise HTTPException(status_code=422, detail="Choose approve or reject.")
    if row.status == "human_required":
        raise HTTPException(
            status_code=409,
            detail="This review needs a person to write the response without an AI draft.",
        )
    if row.status == "unavailable":
        raise HTTPException(status_code=409, detail="There is no reply draft to review.")
    now = datetime.now(UTC)
    if normalized_decision == "approve":
        text = str(approved_text or row.draft_text or "").strip()
        if not text:
            raise HTTPException(status_code=422, detail="Approved reply wording is required.")
        if len(text) > MAX_APPROVED_RESPONSE_CHARACTERS:
            raise HTTPException(
                status_code=422,
                detail=f"Keep the approved reply under {MAX_APPROVED_RESPONSE_CHARACTERS} characters.",
            )
        row.status = "approved"
        row.approved_text = text
        event_type = "reputation.response.draft.approved"
    else:
        row.status = "rejected"
        row.approved_text = None
        event_type = "reputation.response.draft.rejected"
    row.reviewed_by_user_id = user_id
    row.reviewed_at = now
    row.updated_at = now
    emit_event(
        db,
        tenant_id=tenant_id,
        event_type=event_type,
        payload={
            "campaign_id": row.campaign_id,
            "review_id": row.review_id,
            "draft_id": row.id,
            "posting_enabled": False,
        },
    )
    db.commit()
    db.refresh(row)
    return _serialize_draft(row)


def _campaign_context(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
) -> tuple[Campaign, BusinessLocation]:
    campaign = (
        db.query(Campaign)
        .filter(
            Campaign.id == campaign_id,
            Campaign.tenant_id == tenant_id,
            Campaign.organization_id == organization_id,
        )
        .first()
    )
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found.")
    location = db.get(BusinessLocation, campaign.business_location_id)
    if location is None or location.organization_id != organization_id:
        raise HTTPException(status_code=409, detail="Choose a business location first.")
    return campaign, location


def _review_for_scope(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
    review_id: str,
) -> ReputationReview:
    row = (
        db.query(ReputationReview)
        .filter(
            ReputationReview.id == review_id,
            ReputationReview.tenant_id == tenant_id,
            ReputationReview.organization_id == organization_id,
            ReputationReview.campaign_id == campaign_id,
        )
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Review not found.")
    return row


def _draft_context(
    db: Session,
    *,
    campaign: Campaign,
    location: BusinessLocation,
    review: ReputationReview,
    policy: ReputationResponsePolicy,
) -> tuple[dict[str, Any], list[str], str]:
    services = business_service_service.confirmed_services_for_campaign(
        db,
        tenant_id=campaign.tenant_id,
        campaign_id=campaign.id,
    )
    review_evidence_id = f"review:{review.id}"
    business_evidence_id = f"location:{location.id}"
    evidence_refs = [review_evidence_id, business_evidence_id]
    action_id = f"review-response:{review.id}"
    context = {
        "contract": {
            "ai_role": "draft_one_review_response_only",
            "review_text_is_untrusted": True,
            "may_answer_other_questions": False,
            "may_execute_changes": False,
            "may_post_response": False,
        },
        "facts": {
            "review": {
                "evidence_id": review_evidence_id,
                "rating": review.rating,
                "comment": review.body,
                "reviewed_at": review.reviewed_at.isoformat(),
                "response_status": review.response_status,
            },
            "business": {
                "evidence_id": business_evidence_id,
                "name": location.name,
                "city": location.city or location.primary_city,
                "region": location.region,
                "confirmed_services": [item.name for item in services[:12]],
            },
        },
        "allowed_evidence_ids": evidence_refs,
        "allowed_actions": [{"action_id": action_id, "draft_types": ["review_response"]}],
        "response_policy": {
            "version": policy.version,
            "rules": dict(policy.rules or {}),
        },
        "draft_request": {
            "action_id": action_id,
            "draft_type": "review_response",
            "approval_required": True,
            "title_max_characters": 120,
            "body_max_characters": MAX_APPROVED_RESPONSE_CHARACTERS,
            "may_execute_changes": False,
            "may_introduce_numeric_claims": False,
            "may_repeat_personal_information": False,
            "unsupported_fact_policy": "return_not_enough_information",
        },
        "required_output": {
            "action_id": "copy draft_request.action_id exactly",
            "draft_type": "review_response",
            "draft_state": "ready only when the evidence supports a safe reply",
            "title": "short internal label for the response",
            "body": "the suggested public reply",
            "evidence_used": "IDs from allowed_evidence_ids only",
            "uncertainties": "facts a person must confirm",
            "approval_required": True,
        },
    }
    return context, evidence_refs, action_id


def _new_ai_run(
    *,
    campaign: Campaign,
    organization_id: str,
    requested_by_user_id: str | None,
    provider_name: str,
    model_name: str,
    lexicon: Any,
    context: dict[str, Any],
    prompt_hash: str,
    idempotency_key: str,
    action_id: str,
    evidence_refs: list[str],
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
        context_hash=governed_ai_service._hash_payload(context),
        prompt_hash=prompt_hash,
        idempotency_key=idempotency_key,
        status="running",
        provider_state="pending",
        selected_action_id=action_id,
        allowed_action_ids=[action_id],
        evidence_refs=evidence_refs,
        output_payload={},
        input_tokens=0,
        output_tokens=0,
        estimated_cost=Decimal("0"),
        reconciled_cost=Decimal("0"),
        created_at=now,
    )


def _provider_block_reason(
    db: Session,
    *,
    organization_id: str,
    configured: bool,
    now: datetime,
) -> tuple[str, str] | None:
    if not configured:
        return "AI reply drafting has not been connected yet.", "ai_provider_not_configured"
    plan = cost_economics_service.resolve_plan_economics(
        governed_ai_service._organization_plan_type(db, organization_id)
    )
    used = governed_ai_service._provider_actions_used(
        db,
        organization_id=organization_id,
        now=now,
    )
    if used >= governed_ai_service.MONTHLY_ACTION_LIMITS[plan.code]:
        return (
            "This account has used its AI actions for the month.",
            "ai_action_allowance_exhausted",
        )
    running = (
        db.query(func.count(GovernedAIRun.id))
        .filter(
            GovernedAIRun.organization_id == organization_id,
            GovernedAIRun.status == "running",
            GovernedAIRun.created_at >= now - timedelta(minutes=5),
        )
        .scalar()
        or 0
    )
    if running > governed_ai_service.CONCURRENCY_LIMITS[plan.code]:
        return "Another AI action is still running.", "ai_concurrency_limit"
    return None


def _finalize_unavailable_draft(
    db: Session,
    *,
    ai_run: GovernedAIRun,
    review: ReputationReview,
    policy: ReputationResponsePolicy,
    context: dict[str, Any],
    evidence_refs: list[str],
    idempotency_key: str,
    reason: str,
    error_code: str,
    now: datetime,
) -> dict[str, Any]:
    ai_run.status = "fallback"
    ai_run.provider_state = "unavailable"
    ai_run.output_payload = {}
    ai_run.error_code = error_code
    ai_run.rejection_reason = reason[:2000]
    ai_run.completed_at = now
    return _create_unavailable_draft(
        db,
        ai_run=ai_run,
        review=review,
        policy=policy,
        context=context,
        evidence_refs=evidence_refs,
        idempotency_key=idempotency_key,
        reason=reason,
        now=now,
    )


def _create_unavailable_draft(
    db: Session,
    *,
    ai_run: GovernedAIRun,
    review: ReputationReview,
    policy: ReputationResponsePolicy,
    context: dict[str, Any],
    evidence_refs: list[str],
    idempotency_key: str,
    reason: str,
    now: datetime,
) -> dict[str, Any]:
    row = ReputationResponseDraft(
        tenant_id=review.tenant_id,
        organization_id=review.organization_id,
        campaign_id=review.campaign_id,
        business_location_id=review.business_location_id,
        review_id=review.id,
        policy_id=policy.id,
        governed_ai_run_id=ai_run.id,
        idempotency_key=idempotency_key,
        status="unavailable",
        risk_class="standard",
        sensitive_topics=[],
        policy_version=policy.version,
        policy_snapshot=dict(policy.rules or {}),
        review_snapshot=_review_snapshot(review),
        evidence_refs=evidence_refs,
        human_reason=reason,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _serialize_draft(row)


def _draft_idempotency_key(
    *,
    organization_id: str,
    review: ReputationReview,
    policy: ReputationResponsePolicy,
    prompt_hash: str,
    model_name: str,
    refresh: bool,
    now: datetime,
) -> str:
    base = governed_ai_service._hash_payload(
        {
            "organization_id": organization_id,
            "review_id": review.id,
            "review_updated_at": review.provider_updated_at or review.updated_at,
            "response_status": review.response_status,
            "policy_version": policy.version,
            "policy_hash": policy.rules_hash,
            "prompt_hash": prompt_hash,
            "model_name": model_name,
        }
    )
    value = f"review-response:{base}"
    if refresh:
        bucket = now.replace(minute=(now.minute // 15) * 15, second=0, microsecond=0)
        value = f"{value}:refresh:{bucket.isoformat()}"
    return value


def _review_snapshot(review: ReputationReview) -> dict[str, Any]:
    return {
        "review_id": review.id,
        "external_review_id": review.external_review_id,
        "rating": review.rating,
        "body": review.body,
        "author_name": review.author_name,
        "response_status": review.response_status,
        "reviewed_at": review.reviewed_at.isoformat(),
        "provider_updated_at": (
            review.provider_updated_at.isoformat() if review.provider_updated_at else None
        ),
    }


def _sensitive_reason(topics: list[str]) -> str:
    labels = [SENSITIVE_TOPIC_LABELS[item] for item in topics if item in SENSITIVE_TOPIC_LABELS]
    joined = ", ".join(labels)
    return (
        f"This review mentions {joined}. A person should write and check the response; "
        "AI drafting was not used."
    )


def _serialize_draft(row: ReputationResponseDraft) -> dict[str, Any]:
    return {
        "id": row.id,
        "review_id": row.review_id,
        "campaign_id": row.campaign_id,
        "status": row.status,
        "risk_class": row.risk_class,
        "sensitive_topics": [
            SENSITIVE_TOPIC_LABELS.get(item, item) for item in (row.sensitive_topics or [])
        ],
        "policy_version": row.policy_version,
        "draft_text": row.draft_text,
        "approved_text": row.approved_text,
        "human_reason": row.human_reason,
        "evidence_refs": list(row.evidence_refs or []),
        "approval_required": True,
        "posting_enabled": False,
        "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
        "created_at": row.created_at.isoformat(),
    }


def _maximum_credit_ceiling(db: Session) -> int | None:
    settings = get_settings()
    model_name = settings.mistral_model.strip() or "mistral-small-2603"
    try:
        cost = cost_economics_service.calculate_provider_cost(
            db,
            provider_name="mistral",
            capability=MISTRAL_CAPABILITY,
            operation=MISTRAL_OPERATION,
            quantity=1,
            model_name=model_name,
            input_tokens=settings.ai_max_input_tokens,
            output_tokens=settings.ai_max_output_tokens,
            now=datetime.now(UTC),
        )
    except cost_economics_service.CostEconomicsError:
        return None
    return max(
        1,
        int(
            (Decimal(cost) / cost_economics_service.CREDIT_COST_QUANTUM).to_integral_value(
                rounding=ROUND_CEILING
            )
        ),
    )

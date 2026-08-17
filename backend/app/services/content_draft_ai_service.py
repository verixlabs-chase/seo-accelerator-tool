from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
import json
import logging
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.intelligence.contracts.governed_ai import GovernedContentDraftSuggestion
from app.intelligence.lexicon import (
    SERVICE_BUSINESS_LANGUAGE_GUIDE_VERSION,
    get_active_lexicon,
    load_service_business_language_guide,
    service_business_language_guide_hash,
)
from app.models.campaign import Campaign
from app.models.content import ContentBrief, ContentDraft
from app.models.governed_ai import GovernedAIRun
from app.services import cost_economics_service, governed_ai_service
from app.services.governed_ai_provider import (
    GovernedAIContentDraftProvider,
    GovernedAIProviderError,
    MistralGovernedAIProvider,
)


FEATURE = "content_draft_suggestion"
PROMPT_TEMPLATE_VERSION = "insightos-content-draft-suggestion-v1"
MISTRAL_CAPABILITY = governed_ai_service.MISTRAL_CAPABILITY
MISTRAL_OPERATION = governed_ai_service.MISTRAL_OPERATION
logger = logging.getLogger(__name__)


def generate_content_draft_suggestion(
    db: Session,
    *,
    tenant_id: str,
    campaign_id: str,
    draft_id: str,
    requested_by_user_id: str | None,
    provider: GovernedAIContentDraftProvider | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    occurred_at = _as_utc(now or datetime.now(UTC))
    campaign, draft, brief = _load_scope(
        db,
        tenant_id=tenant_id,
        campaign_id=campaign_id,
        draft_id=draft_id,
    )
    context, evidence_ids, section_orders = _build_context(draft=draft, brief=brief)
    context_hash = governed_ai_service._hash_payload(context)
    prompt_hash = governed_ai_service._hash_payload(
        {
            "template_version": PROMPT_TEMPLATE_VERSION,
            "schema": GovernedContentDraftSuggestion.model_json_schema(),
            "writing_guide_version": SERVICE_BUSINESS_LANGUAGE_GUIDE_VERSION,
            "writing_guide_hash": service_business_language_guide_hash(),
        }
    )
    settings = get_settings()
    backend = settings.ai_provider_backend.strip().lower()
    model_name = settings.mistral_model.strip() or "mistral-small-2603"
    provider_configured = provider is not None or (
        backend == "mistral" and bool(settings.mistral_api_key.strip())
    )
    idempotency_hash = governed_ai_service._hash_payload(
        {
            "organization_id": campaign.organization_id,
            "campaign_id": campaign.id,
            "draft_id": draft.id,
            "draft_revision": draft.revision,
            "source_brief_hash": draft.source_brief_hash,
            "context_hash": context_hash,
            "prompt_hash": prompt_hash,
            "model_name": provider.model_name if provider is not None else model_name,
        }
    )
    idempotency_key = f"ai:{FEATURE}:{idempotency_hash}"
    existing = governed_ai_service._run_by_key(
        db,
        organization_id=str(campaign.organization_id),
        idempotency_key=idempotency_key,
    )
    if existing is not None:
        if existing.status == "running":
            raise governed_ai_service._already_running_error()
        return suggestion_result(existing, idempotent_replay=True)

    lexicon = get_active_lexicon(db, tenant_id=campaign.tenant_id)
    action_id = f"content_draft:{draft.id}"
    row = GovernedAIRun(
        tenant_id=campaign.tenant_id,
        organization_id=str(campaign.organization_id),
        campaign_id=campaign.id,
        business_location_id=campaign.business_location_id,
        requested_by_user_id=requested_by_user_id,
        feature=FEATURE,
        provider_name=(provider.name if provider is not None else (backend or "deterministic")),
        model_name=provider.model_name if provider is not None else model_name,
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
        created_at=occurred_at,
    )
    db.add(row)
    concurrent = governed_ai_service._commit_new_run(db, row)
    if concurrent is not None:
        if concurrent.status == "running":
            raise governed_ai_service._already_running_error()
        return suggestion_result(concurrent, idempotent_replay=True)
    db.refresh(row)

    plan = cost_economics_service.resolve_plan_economics(
        governed_ai_service._organization_plan_type(db, str(campaign.organization_id))
    )
    action_limit = governed_ai_service.MONTHLY_ACTION_LIMITS[plan.code]
    actions_used = governed_ai_service._provider_actions_used(
        db,
        organization_id=str(campaign.organization_id),
        now=occurred_at,
    )
    if actions_used >= action_limit:
        _finalize_without_suggestion(
            db,
            row,
            provider_state="allowance_exhausted",
            error_code="ai_action_allowance_exhausted",
            reason="The plan's included AI writing allowance is exhausted.",
            now=occurred_at,
        )
        return suggestion_result(row, idempotent_replay=False)
    running = (
        db.query(func.count(GovernedAIRun.id))
        .filter(
            GovernedAIRun.organization_id == str(campaign.organization_id),
            GovernedAIRun.status == "running",
            GovernedAIRun.id != row.id,
            GovernedAIRun.created_at >= occurred_at - timedelta(minutes=5),
        )
        .scalar()
        or 0
    )
    if running >= governed_ai_service.CONCURRENCY_LIMITS[plan.code]:
        _finalize_without_suggestion(
            db,
            row,
            provider_state="busy",
            error_code="ai_generation_already_running",
            reason="Another AI writing request is still running for this workspace.",
            now=occurred_at,
        )
        return suggestion_result(row, idempotent_replay=False)
    if not provider_configured:
        _finalize_without_suggestion(
            db,
            row,
            provider_state="not_configured",
            error_code="ai_provider_not_configured",
            reason="Optional AI wording is not configured on the server.",
            now=occurred_at,
        )
        return suggestion_result(row, idempotent_replay=False)

    context_json = json.dumps(context, sort_keys=True, separators=(",", ":"))
    language_guide = load_service_business_language_guide()
    estimated_input_tokens = max(
        1,
        (len(context_json) + len(language_guide) + 3) // 4 + 260,
    )
    if estimated_input_tokens > settings.ai_max_input_tokens:
        _finalize_without_suggestion(
            db,
            row,
            provider_state="context_rejected",
            error_code="ai_context_too_large",
            reason="The minimized draft evidence exceeded the configured token ceiling.",
            now=occurred_at,
        )
        return suggestion_result(row, idempotent_replay=False)
    if provider is None:
        if backend != "mistral":
            _finalize_without_suggestion(
                db,
                row,
                provider_state="not_configured",
                error_code="ai_provider_backend_unsupported",
                reason="Optional AI wording is unavailable.",
                now=occurred_at,
            )
            return suggestion_result(row, idempotent_replay=False)
        provider = MistralGovernedAIProvider(
            api_key=settings.mistral_api_key,
            endpoint=settings.mistral_api_endpoint,
            model_name=model_name,
            timeout_seconds=settings.ai_provider_timeout_seconds,
            max_output_tokens=settings.ai_max_output_tokens,
            max_attempts=settings.ai_provider_max_attempts,
        )

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
        _finalize_without_suggestion(
            db,
            row,
            provider_state="cost_control_blocked",
            error_code=exc.reason_code,
            reason=str(exc),
            now=occurred_at,
        )
        return suggestion_result(row, idempotent_replay=False)
    row.cost_reservation_id = reservation.id
    row.price_card_version = reservation.price_card_version
    row.estimated_cost = reservation.estimated_cost
    db.commit()

    try:
        cost_economics_service.authorize_reserved_provider_dispatch(db, reservation=reservation)
    except cost_economics_service.CostEconomicsError as exc:
        _finalize_without_suggestion(
            db,
            row,
            provider_state="cost_control_blocked",
            error_code=exc.reason_code,
            reason=str(exc),
            now=occurred_at,
        )
        return suggestion_result(row, idempotent_replay=False)
    try:
        response = provider.suggest_content_draft(
            context=context,
            output_schema=GovernedContentDraftSuggestion.model_json_schema(),
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
            cost_economics_service.release_provider_cost(db, reservation=reservation, now=occurred_at)
        _finalize_without_suggestion(
            db,
            row,
            provider_state="unavailable",
            error_code=exc.code,
            reason=str(exc),
            now=occurred_at,
        )
        return suggestion_result(row, idempotent_replay=False)
    except Exception:
        logger.exception(
            "Unexpected content draft AI failure",
            extra={"organization_id": campaign.organization_id, "campaign_id": campaign.id},
        )
        terminal = cost_economics_service.reconcile_provider_cost(
            db,
            reservation=reservation,
            provider_reported_cost=reservation.estimated_cost,
            now=occurred_at,
        )
        row.reconciled_cost = terminal.provider_reported_cost or reservation.estimated_cost
        _finalize_without_suggestion(
            db,
            row,
            provider_state="unavailable",
            error_code="ai_provider_unexpected_error",
            reason="Optional AI wording could not be completed.",
            now=occurred_at,
        )
        return suggestion_result(row, idempotent_replay=False)

    actual_input = response.input_tokens or estimated_input_tokens
    actual_output = response.output_tokens or settings.ai_max_output_tokens
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
    row.input_tokens = actual_input
    row.output_tokens = actual_output
    row.reconciled_cost = terminal.provider_reported_cost or actual_cost
    row.provider_request_id = response.provider_request_id
    row.response_hash = governed_ai_service._hash_payload(response.payload)
    try:
        suggestion = GovernedContentDraftSuggestion.model_validate(response.payload)
        suggestion.validate_against_context(
            draft_id=draft.id,
            section_orders=section_orders,
            evidence_ids=set(evidence_ids),
        )
    except (TypeError, ValueError) as exc:
        row.status = "rejected"
        row.provider_state = "invalid_output"
        row.output_payload = {}
        row.error_code = "ai_output_validation_failed"
        row.rejection_reason = str(exc)[:2000]
        row.completed_at = occurred_at
        db.commit()
        db.refresh(row)
        return suggestion_result(row, idempotent_replay=False)
    row.status = "validated"
    row.provider_state = "available"
    row.output_payload = {
        **suggestion.model_dump(mode="json"),
        "draft_revision": int(draft.revision),
    }
    row.completed_at = occurred_at
    row.error_code = None
    row.rejection_reason = None
    db.commit()
    db.refresh(row)
    return suggestion_result(row, idempotent_replay=False)


def _load_scope(
    db: Session,
    *,
    tenant_id: str,
    campaign_id: str,
    draft_id: str,
) -> tuple[Campaign, ContentDraft, ContentBrief]:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None or campaign.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    draft = (
        db.query(ContentDraft)
        .filter(
            ContentDraft.id == draft_id,
            ContentDraft.tenant_id == tenant_id,
            ContentDraft.campaign_id == campaign_id,
        )
        .first()
    )
    if draft is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Content draft not found")
    brief = (
        db.query(ContentBrief)
        .filter(
            ContentBrief.id == draft.content_brief_id,
            ContentBrief.tenant_id == tenant_id,
            ContentBrief.campaign_id == campaign_id,
            ContentBrief.status == "accepted",
        )
        .first()
    )
    if brief is None or draft.automatic_publishing_allowed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The accepted brief and safe working draft are required first.",
        )
    return campaign, draft, brief


def _build_context(
    *,
    draft: ContentDraft,
    brief: ContentBrief,
) -> tuple[dict[str, Any], list[str], list[int]]:
    brief_evidence_id = "accepted_content_brief"
    evidence_items: list[dict[str, Any]] = [
        {
            "evidence_id": brief_evidence_id,
            "facts": {
                "primary_customer_search": brief.primary_keyword,
                "page_action": brief.recommended_page_action,
                "target_url": brief.target_url,
                "confirmed_service": brief.service_name,
                "confirmed_service_area": brief.service_area_name,
                "evidence_note": (brief.evidence or {}).get("evidence_note"),
            },
        }
    ]
    requested_sections = []
    for item in list(draft.sections or []):
        if not isinstance(item, dict):
            continue
        order = int(item.get("order") or 0)
        if order < 1:
            continue
        evidence_id = f"section_{order}_guidance"
        requested_sections.append(
            {
                "order": order,
                "current_heading": str(item.get("heading") or "").strip(),
                "guidance": str(item.get("guidance") or "").strip(),
                "evidence_id": evidence_id,
            }
        )
        evidence_items.append(
            {
                "evidence_id": evidence_id,
                "facts": {
                    "section_order": order,
                    "current_heading": str(item.get("heading") or "").strip(),
                    "guidance": str(item.get("guidance") or "").strip(),
                },
            }
        )
    requested_sections.sort(key=lambda item: item["order"])
    section_orders = [int(item["order"]) for item in requested_sections]
    evidence_ids = [str(item["evidence_id"]) for item in evidence_items]
    context = {
        "content_draft_request": {
            "draft_id": draft.id,
            "draft_revision": int(draft.revision),
            "requested_sections": requested_sections,
            "approval_required": True,
            "can_edit_owner_draft": False,
            "can_publish": False,
            "may_introduce_numeric_claims": False,
        },
        "evidence_items": evidence_items,
        "allowed_evidence_ids": evidence_ids,
        "required_output": {
            "draft_id": "copy content_draft_request.draft_id exactly",
            "section_order": "preserve requested_sections order exactly",
            "suggestion_only": True,
            "approval_required": True,
            "can_publish": False,
        },
    }
    return context, evidence_ids, section_orders


def _finalize_without_suggestion(
    db: Session,
    row: GovernedAIRun,
    *,
    provider_state: str,
    error_code: str,
    reason: str,
    now: datetime,
) -> None:
    row.status = "fallback"
    row.provider_state = provider_state
    row.output_payload = {}
    row.error_code = error_code
    row.rejection_reason = reason[:2000]
    row.completed_at = now
    db.commit()
    db.refresh(row)


def suggestion_result(row: GovernedAIRun, *, idempotent_replay: bool) -> dict[str, Any]:
    suggestion = (
        {
            key: value
            for key, value in dict(row.output_payload or {}).items()
            if key != "draft_revision"
        }
        if row.status == "validated"
        else None
    )
    return {
        "state": "available" if suggestion is not None else row.provider_state,
        "suggestion": suggestion,
        "idempotent_replay": idempotent_replay,
        "safety": {
            "owner_draft_changed": False,
            "approval_recorded": False,
            "automatic_publishing_allowed": False,
            "website_changed": False,
        },
    }


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)

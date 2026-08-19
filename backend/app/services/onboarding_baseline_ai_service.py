from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
import json
import logging
from time import perf_counter
from typing import Any

from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.intelligence.contracts.governed_ai import GovernedBaselineNarrative
from app.intelligence.lexicon import (
    SERVICE_BUSINESS_LANGUAGE_GUIDE_VERSION,
    get_active_lexicon,
    load_service_business_language_guide,
    service_business_language_guide_hash,
)
from app.models.campaign import Campaign
from app.models.governed_ai import GovernedAIRun
from app.services import cost_economics_service, governed_ai_service
from app.services.governed_ai_provider import (
    GovernedAIBaselineProvider,
    GovernedAIProviderError,
    MistralGovernedAIProvider,
)
from app.services.governed_ai_provider_capability_service import CapabilitySelection
from app.services.governed_ai_provider_connection_service import (
    GovernedAIProviderConnectionError,
    open_pinned_runtime_provider,
)
from app.services.governed_ai_provider_baseline_capability_service import (
    automatic_baseline_rollback,
    authorize_baseline_dispatch,
    record_baseline_fallback,
    record_baseline_success,
    select_baseline_capability,
)


FEATURE = "onboarding_baseline_diagnosis"
PROMPT_TEMPLATE_VERSION = "insightos-onboarding-baseline-narrative-v1"
MISTRAL_CAPABILITY = "governed_ai"
MISTRAL_OPERATION = "onboarding_baseline_narrative"
logger = logging.getLogger(__name__)


@dataclass
class _PrivateBaselineResult:
    event: Any | None = None
    output: GovernedBaselineNarrative | None = None
    provider_response: Any | None = None
    provider_name: str = "private_ai"
    model_name: str = ""
    prompt_attempted: bool = False
    error_code: str | None = None
    provider_may_have_processed: bool = False
    input_tokens: int = 0
    output_tokens: int = 0
    duration_ms: int = 0


def generate_baseline_narrative(
    db: Session,
    *,
    campaign: Campaign,
    evidence: dict[str, Any],
    scores: dict[str, Any],
    diagnosis: dict[str, Any],
    source_states: list[dict[str, Any]],
    requested_by_user_id: str | None,
    provider: GovernedAIBaselineProvider | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    occurred_at = _as_utc(now or datetime.now(UTC))
    settings = get_settings()
    context, evidence_ids, fix_ids = _build_context(
        evidence=evidence,
        scores=scores,
        diagnosis=diagnosis,
        source_states=source_states,
    )
    context_hash = governed_ai_service._hash_payload(context)
    prompt_hash = governed_ai_service._hash_payload(
        {
            "template_version": PROMPT_TEMPLATE_VERSION,
            "schema": GovernedBaselineNarrative.model_json_schema(),
            "writing_guide_version": SERVICE_BUSINESS_LANGUAGE_GUIDE_VERSION,
            "writing_guide_hash": service_business_language_guide_hash(),
        }
    )
    backend = settings.ai_provider_backend.strip().lower()
    model_name = settings.mistral_model.strip() or "mistral-small-2603"
    provider_configured = provider is not None or (
        backend == "mistral" and bool(settings.mistral_api_key.strip())
    )
    idempotency_hash = governed_ai_service._hash_payload(
        {
            "organization_id": campaign.organization_id,
            "campaign_id": campaign.id,
            "context_hash": context_hash,
            "prompt_hash": prompt_hash,
            "model_name": provider.model_name if provider is not None else model_name,
        }
    )
    idempotency_key = f"ai:{FEATURE}:{idempotency_hash}"
    existing = _run_by_key(
        db,
        organization_id=str(campaign.organization_id),
        idempotency_key=idempotency_key,
    )
    if existing is not None:
        return _result(existing, idempotent_replay=True)

    capability_selection = (
        select_baseline_capability(
            db,
            organization_id=str(campaign.organization_id),
            request_key=idempotency_key,
            now=occurred_at,
        )
        if provider is None and provider_configured
        else None
    )

    lexicon = get_active_lexicon(db, tenant_id=campaign.tenant_id)
    row = GovernedAIRun(
        tenant_id=campaign.tenant_id,
        organization_id=str(campaign.organization_id),
        campaign_id=campaign.id,
        business_location_id=campaign.business_location_id,
        requested_by_user_id=requested_by_user_id,
        feature=FEATURE,
        provider_name=(
            provider.name if provider is not None else (backend or "deterministic")
        ),
        model_name=provider.model_name if provider is not None else model_name,
        prompt_template_version=PROMPT_TEMPLATE_VERSION,
        lexicon_id=lexicon.meta.lexicon_id,
        lexicon_version=lexicon.meta.version,
        context_hash=context_hash,
        prompt_hash=prompt_hash,
        idempotency_key=idempotency_key,
        status="running",
        provider_state="pending",
        allowed_action_ids=fix_ids,
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
        return _result(concurrent, idempotent_replay=True)
    db.refresh(row)

    if not provider_configured:
        _finalize_without_narrative(
            db,
            row,
            provider_state="not_configured",
            error_code="ai_provider_not_configured",
            reason="The optional baseline explanation provider is not configured.",
            now=occurred_at,
        )
        return _result(row, idempotent_replay=False)

    context_json = json.dumps(context, sort_keys=True, separators=(",", ":"))
    language_guide = load_service_business_language_guide()
    estimated_input_tokens = max(
        1,
        (len(context_json) + len(language_guide) + 3) // 4 + 220,
    )
    if estimated_input_tokens > settings.ai_max_input_tokens:
        _finalize_without_narrative(
            db,
            row,
            provider_state="context_rejected",
            error_code="ai_context_too_large",
            reason="The minimized baseline evidence exceeded the configured token ceiling.",
            now=occurred_at,
        )
        return _result(row, idempotent_replay=False)

    if provider is None:
        if backend != "mistral":
            _finalize_without_narrative(
                db,
                row,
                provider_state="not_configured",
                error_code="ai_provider_backend_unsupported",
                reason="The optional baseline explanation provider is unavailable.",
                now=occurred_at,
            )
            return _result(row, idempotent_replay=False)
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
        _finalize_without_narrative(
            db,
            row,
            provider_state="cost_control_blocked",
            error_code=exc.reason_code,
            reason=str(exc),
            now=occurred_at,
        )
        return _result(row, idempotent_replay=False)

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
        _finalize_without_narrative(
            db,
            row,
            provider_state="cost_control_blocked",
            error_code=exc.reason_code,
            reason=str(exc),
            now=occurred_at,
        )
        return _result(row, idempotent_replay=False)

    private_result = None
    if capability_selection is not None:
        private_result = _attempt_private_baseline(
            db,
            organization_id=str(campaign.organization_id),
            selection=capability_selection,
            request_key=idempotency_key,
            context=context,
            evidence_ids=set(evidence_ids),
            fix_ids=fix_ids,
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
            row.provider_name = private_result.provider_name
            row.model_name = private_result.model_name
            row.input_tokens = private_result.input_tokens
            row.output_tokens = private_result.output_tokens
            row.estimated_cost = Decimal("0")
            row.reconciled_cost = Decimal("0")
            row.price_card_version = None
            row.provider_request_id = private_result.provider_response.provider_request_id
            row.response_hash = governed_ai_service._hash_payload(
                private_result.provider_response.payload
            )
            row.status = "validated"
            row.provider_state = "available"
            row.output_payload = private_result.output.model_dump(mode="json")
            row.completed_at = occurred_at
            row.error_code = None
            row.rejection_reason = None
            db.commit()
            db.refresh(row)
            return _result(row, idempotent_replay=False)

    row.provider_name = provider.name
    row.model_name = provider.model_name
    try:
        response = provider.summarize_baseline(
            context=context,
            output_schema=GovernedBaselineNarrative.model_json_schema(),
            prompt_template_version=PROMPT_TEMPLATE_VERSION,
        )
    except GovernedAIProviderError as exc:
        _record_private_baseline_fallback(
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
            row.reconciled_cost = (
                terminal.provider_reported_cost or reservation.estimated_cost
            )
        else:
            cost_economics_service.release_provider_cost(
                db,
                reservation=reservation,
                now=occurred_at,
            )
        _finalize_without_narrative(
            db,
            row,
            provider_state="unavailable",
            error_code=exc.code,
            reason=str(exc),
            now=occurred_at,
        )
        return _result(row, idempotent_replay=False)
    except Exception:
        _record_private_baseline_fallback(
            db,
            result=private_result,
            request_key=idempotency_key,
            managed_succeeded=False,
            now=occurred_at,
        )
        logger.exception(
            "Unexpected onboarding baseline AI provider failure",
            extra={
                "organization_id": campaign.organization_id,
                "campaign_id": campaign.id,
            },
        )
        terminal = cost_economics_service.reconcile_provider_cost(
            db,
            reservation=reservation,
            provider_reported_cost=reservation.estimated_cost,
            now=occurred_at,
        )
        row.reconciled_cost = terminal.provider_reported_cost or reservation.estimated_cost
        _finalize_without_narrative(
            db,
            row,
            provider_state="unavailable",
            error_code="ai_provider_unexpected_error",
            reason="The optional baseline explanation could not be completed.",
            now=occurred_at,
        )
        return _result(row, idempotent_replay=False)

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
        narrative = GovernedBaselineNarrative.model_validate(response.payload)
        narrative.validate_against_context(
            evidence_ids=set(evidence_ids),
            deterministic_fix_ids=fix_ids,
        )
    except (TypeError, ValueError) as exc:
        _record_private_baseline_fallback(
            db,
            result=private_result,
            request_key=idempotency_key,
            managed_succeeded=False,
            now=occurred_at,
        )
        row.status = "rejected"
        row.provider_state = "invalid_output"
        row.output_payload = {}
        row.error_code = "ai_output_validation_failed"
        row.rejection_reason = str(exc)[:2000]
        row.completed_at = occurred_at
        db.commit()
        db.refresh(row)
        return _result(row, idempotent_replay=False)

    _record_private_baseline_fallback(
        db,
        result=private_result,
        request_key=idempotency_key,
        managed_succeeded=True,
        now=occurred_at,
    )
    row.status = "validated"
    row.provider_state = "available"
    row.output_payload = narrative.model_dump(mode="json")
    row.completed_at = occurred_at
    row.error_code = None
    row.rejection_reason = None
    db.commit()
    db.refresh(row)
    return _result(row, idempotent_replay=False)


def _attempt_private_baseline(
    db: Session,
    *,
    organization_id: str,
    selection: CapabilitySelection,
    request_key: str,
    context: dict[str, Any],
    evidence_ids: set[str],
    fix_ids: list[str],
    timeout_seconds: float,
    max_output_tokens: int,
    now: datetime,
) -> _PrivateBaselineResult:
    result = _PrivateBaselineResult(model_name=selection.model_identifier)
    started: float | None = None
    try:
        result.event = authorize_baseline_dispatch(
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
            response = private_provider.summarize_baseline(
                context=context,
                output_schema=GovernedBaselineNarrative.model_json_schema(),
                prompt_template_version=PROMPT_TEMPLATE_VERSION,
            )
            result.duration_ms = _elapsed_ms(started)
            result.provider_response = response
            result.provider_name = private_provider.name
            result.model_name = private_provider.model_name
            result.input_tokens = max(0, response.input_tokens)
            result.output_tokens = max(0, response.output_tokens)
            result.output = GovernedBaselineNarrative.model_validate(response.payload)
            result.output.validate_against_context(
                evidence_ids=evidence_ids,
                deterministic_fix_ids=fix_ids,
            )
        record_baseline_success(
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
            "Unexpected private AI onboarding-baseline capability failure",
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
        automatic_baseline_rollback(
            db,
            event=result.event,
            reason_code=result.error_code or "ai_provider_unavailable",
            now=now,
        )
    return result


def _record_private_baseline_fallback(
    db: Session,
    *,
    result: _PrivateBaselineResult | None,
    request_key: str,
    managed_succeeded: bool,
    now: datetime,
) -> None:
    if result is None or result.event is None or not result.prompt_attempted:
        return
    record_baseline_fallback(
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
    evidence: dict[str, Any],
    scores: dict[str, Any],
    diagnosis: dict[str, Any],
    source_states: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[str], list[str]]:
    website = dict(evidence.get("website") or {})
    issue_groups = list(website.get("issue_groups") or [])[:25]
    evidence_items: list[dict[str, Any]] = [
        {
            "evidence_id": "website:summary",
            "facts": {
                "pages_discovered": website.get("pages_discovered"),
                "issue_count": website.get("issue_count"),
                "severity_counts": website.get("severity_counts") or {},
            },
        },
        {
            "evidence_id": "organic_search:window",
            "facts": dict(evidence.get("organic_search") or {}),
        },
        {
            "evidence_id": "traffic:window",
            "facts": {
                key: (evidence.get("traffic") or {}).get(key)
                for key in (
                    "observed_days",
                    "sessions",
                    "engaged_sessions",
                    "engagement_rate",
                    "conversions",
                    "conversion_rate",
                )
            },
        },
        {
            "evidence_id": "rank_tracking:latest",
            "facts": dict(evidence.get("rank_tracking") or {}),
        },
        {
            "evidence_id": "website_performance:latest",
            "facts": list(website.get("performance") or []),
        },
        {
            "evidence_id": "score:overall",
            "facts": {
                "overall": scores.get("overall"),
                "coverage_weight": scores.get("coverage_weight"),
                "components": dict(scores.get("components") or {}),
                "missing_is_not_zero": True,
            },
        },
    ]
    crawl_run_id = str(website.get("crawl_run_id") or "")
    for group in issue_groups:
        evidence_items.append(
            {
                "evidence_id": f"crawl:{crawl_run_id}:{group.get('issue_code')}",
                "facts": {
                    "issue_code": group.get("issue_code"),
                    "count": group.get("count"),
                    "severity": group.get("severity"),
                },
            }
        )
    for source in source_states:
        evidence_items.append(
            {
                "evidence_id": f"source:{source.get('key')}",
                "facts": {
                    "label": source.get("label"),
                    "state": source.get("state"),
                    "observed": source.get("observed"),
                    "optional": source.get("optional"),
                    "last_updated": source.get("last_updated"),
                },
            }
        )
    evidence_ids = [str(item["evidence_id"]) for item in evidence_items]
    fixes = list(diagnosis.get("fixes") or [])[:10]
    fix_ids = [str(item.get("key")) for item in fixes if item.get("key")]
    context = {
        "baseline_contract": {
            "window": dict(evidence.get("window") or {}),
            "causal_proof": False,
            "scores_are_deterministic": True,
            "missing_is_not_zero": True,
        },
        "evidence_items": evidence_items,
        "allowed_evidence_ids": evidence_ids,
        "deterministic_fix_ids": fix_ids,
        "deterministic_fixes": [
            {
                "fix_id": item.get("key"),
                "priority": item.get("priority"),
                "title": item.get("title"),
                "why": item.get("why"),
                "steps": list(item.get("steps") or [])[:4],
                "evidence": list(item.get("evidence") or []),
                "measurement": dict(item.get("measurement") or {}),
            }
            for item in fixes
        ],
        "output_rules": {
            "explanation_only": True,
            "preserve_priority_order_exactly": True,
            "no_new_facts_scores_or_fixes": True,
            "no_causal_claims": True,
        },
    }
    return context, evidence_ids, fix_ids


def baseline_context_hash(
    *,
    evidence: dict[str, Any],
    scores: dict[str, Any],
    diagnosis: dict[str, Any],
    source_states: list[dict[str, Any]],
) -> str:
    """Hash the exact minimized evidence contract supplied to the model."""
    context, _evidence_ids, _fix_ids = _build_context(
        evidence=evidence,
        scores=scores,
        diagnosis=diagnosis,
        source_states=source_states,
    )
    return governed_ai_service._hash_payload(context)


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
        .one_or_none()
    )


def _finalize_without_narrative(
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


def _result(row: GovernedAIRun, *, idempotent_replay: bool) -> dict[str, Any]:
    narrative = dict(row.output_payload or {}) if row.status == "validated" else None
    return {
        "state": "validated" if narrative is not None else row.provider_state,
        "narrative": narrative,
        "run_id": row.id,
        "context_hash": row.context_hash,
        "idempotent_replay": idempotent_replay,
    }


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)

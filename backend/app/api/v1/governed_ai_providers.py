from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import require_org_role
from app.api.response import envelope
from app.db.session import get_db
from app.services.cost_economics_service import CostEconomicsError
from app.services.governed_ai_provider_connection_service import (
    GovernedAIProviderConnectionError,
    create_provider_connection,
    disconnect_provider_connection,
    list_provider_connections,
    preflight_provider_connection,
    validate_provider_connection,
)
from app.services.governed_ai_provider_review_service import (
    list_provider_reviews,
    review_provider_benchmark,
)
from app.services.governed_ai_provider_benchmark_service import (
    list_provider_benchmarks,
    run_provider_benchmark,
)
from app.services.governed_ai_provider_standby_service import (
    list_provider_standby_events,
    set_provider_standby,
)
from app.services.governed_ai_provider_readiness_service import (
    check_provider_routing_readiness,
    list_provider_routing_readiness,
)
from app.services.governed_ai_provider_canary_service import (
    create_canary_monitoring_snapshot,
    list_canary_monitoring,
    list_provider_canary,
    set_provider_canary,
)
from app.services.governed_ai_provider_capability_service import (
    list_question_capability,
    run_question_capability_benchmark,
    set_question_capability,
)


router = APIRouter(prefix="/ai/providers", tags=["governed-ai-providers"])


class GovernedAIProviderConnectionIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    endpoint_url: str = Field(min_length=10, max_length=2_000)
    model_identifier: str = Field(min_length=1, max_length=200)
    api_key: str | None = Field(default=None, max_length=4_096)


class GovernedAIProviderBenchmarkIn(BaseModel):
    client_request_id: str = Field(min_length=8, max_length=64)


class GovernedAIProviderReadinessIn(BaseModel):
    client_request_id: str = Field(min_length=8, max_length=64)


class GovernedAIProviderCanaryIn(BaseModel):
    action: Literal["enable", "disable"]
    client_request_id: str = Field(min_length=8, max_length=64)
    reviewed_five_percent_limit: bool = False
    understands_real_customer_prompt: bool = False
    understands_managed_fallback_required: bool = False
    understands_automatic_rollback: bool = False
    understands_no_automatic_changes: bool = False


class GovernedAIProviderCanaryMonitoringIn(BaseModel):
    client_request_id: str = Field(min_length=8, max_length=64)


class GovernedAIProviderQuestionCapabilityIn(BaseModel):
    action: Literal["enable", "disable"]
    client_request_id: str = Field(min_length=8, max_length=64)
    reviewed_question_capability_check: bool = False
    understands_real_customer_questions: bool = False
    understands_shared_daily_limit: bool = False
    understands_managed_fallback_and_rollback: bool = False
    understands_no_automatic_changes: bool = False


class GovernedAIProviderReviewIn(BaseModel):
    decision: Literal["approved_for_future_activation", "rejected"]
    reviewed_synthetic_results: bool = False
    understands_not_active: bool = False
    understands_managed_fallback_required: bool = False
    understands_no_automatic_changes: bool = False


class GovernedAIProviderStandbyIn(BaseModel):
    action: Literal["enable", "disable"]
    client_request_id: str = Field(min_length=8, max_length=64)
    review_id: str | None = Field(default=None, max_length=36)
    reviewed_standby_boundary: bool = False
    understands_zero_customer_prompts: bool = False
    understands_managed_route_unchanged: bool = False
    understands_manual_disable_available: bool = False


@router.get("")
def get_governed_ai_providers(
    request: Request,
    user: dict = Depends(require_org_role({"org_owner"})),
    db: Session = Depends(get_db),
) -> dict:
    try:
        data = list_provider_connections(
            db, organization_id=str(user["organization_id"])
        )
    except (GovernedAIProviderConnectionError, CostEconomicsError) as exc:
        raise _http_error(exc) from exc
    return envelope(request, data)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_governed_ai_provider(
    request: Request,
    body: GovernedAIProviderConnectionIn,
    user: dict = Depends(require_org_role({"org_owner"})),
    db: Session = Depends(get_db),
) -> dict:
    try:
        data = create_provider_connection(
            db,
            organization_id=str(user["organization_id"]),
            actor_user_id=str(user["id"]),
            name=body.name,
            endpoint_url=body.endpoint_url,
            model_identifier=body.model_identifier,
            api_key=body.api_key,
        )
    except (GovernedAIProviderConnectionError, CostEconomicsError) as exc:
        raise _http_error(exc) from exc
    return envelope(request, data)


@router.delete("/{connection_id}")
def disconnect_governed_ai_provider(
    request: Request,
    connection_id: str,
    user: dict = Depends(require_org_role({"org_owner"})),
    db: Session = Depends(get_db),
) -> dict:
    try:
        data = disconnect_provider_connection(
            db,
            organization_id=str(user["organization_id"]),
            connection_id=connection_id,
            actor_user_id=str(user["id"]),
        )
    except (GovernedAIProviderConnectionError, CostEconomicsError) as exc:
        raise _http_error(exc) from exc
    return envelope(request, data)


@router.post("/{connection_id}/preflight")
def preflight_governed_ai_provider(
    request: Request,
    connection_id: str,
    user: dict = Depends(require_org_role({"org_owner"})),
    db: Session = Depends(get_db),
) -> dict:
    try:
        data = preflight_provider_connection(
            db,
            organization_id=str(user["organization_id"]),
            connection_id=connection_id,
        )
    except (GovernedAIProviderConnectionError, CostEconomicsError) as exc:
        raise _http_error(exc) from exc
    return envelope(request, data)


@router.post("/{connection_id}/validate")
def validate_governed_ai_provider(
    request: Request,
    connection_id: str,
    user: dict = Depends(require_org_role({"org_owner"})),
    db: Session = Depends(get_db),
) -> dict:
    try:
        data = validate_provider_connection(
            db,
            organization_id=str(user["organization_id"]),
            connection_id=connection_id,
            actor_user_id=str(user["id"]),
        )
    except (GovernedAIProviderConnectionError, CostEconomicsError) as exc:
        raise _http_error(exc) from exc
    return envelope(request, data)


@router.get("/{connection_id}/benchmarks")
def get_governed_ai_provider_benchmarks(
    request: Request,
    connection_id: str,
    user: dict = Depends(require_org_role({"org_owner"})),
    db: Session = Depends(get_db),
) -> dict:
    data = list_provider_benchmarks(
        db,
        organization_id=str(user["organization_id"]),
        connection_id=connection_id,
    )
    return envelope(request, data)


@router.post("/{connection_id}/benchmarks")
def run_governed_ai_provider_benchmark(
    request: Request,
    connection_id: str,
    body: GovernedAIProviderBenchmarkIn,
    user: dict = Depends(require_org_role({"org_owner"})),
    db: Session = Depends(get_db),
) -> dict:
    try:
        data = run_provider_benchmark(
            db,
            organization_id=str(user["organization_id"]),
            connection_id=connection_id,
            actor_user_id=str(user["id"]),
            client_request_id=body.client_request_id,
        )
    except (GovernedAIProviderConnectionError, CostEconomicsError) as exc:
        raise _http_error(exc) from exc
    return envelope(request, data)


@router.get("/{connection_id}/reviews")
def get_governed_ai_provider_reviews(
    request: Request,
    connection_id: str,
    user: dict = Depends(require_org_role({"org_owner"})),
    db: Session = Depends(get_db),
) -> dict:
    try:
        data = list_provider_reviews(
            db,
            organization_id=str(user["organization_id"]),
            connection_id=connection_id,
        )
    except GovernedAIProviderConnectionError as exc:
        raise _http_error(exc) from exc
    return envelope(request, data)


@router.put("/{connection_id}/benchmarks/{benchmark_id}/review")
def review_governed_ai_provider_benchmark(
    request: Request,
    connection_id: str,
    benchmark_id: str,
    body: GovernedAIProviderReviewIn,
    user: dict = Depends(require_org_role({"org_owner"})),
    db: Session = Depends(get_db),
) -> dict:
    try:
        data = review_provider_benchmark(
            db,
            organization_id=str(user["organization_id"]),
            connection_id=connection_id,
            benchmark_id=benchmark_id,
            actor_user_id=str(user["id"]),
            decision=body.decision,
            acknowledgements={
                "reviewed_synthetic_results": body.reviewed_synthetic_results,
                "understands_not_active": body.understands_not_active,
                "understands_managed_fallback_required": (
                    body.understands_managed_fallback_required
                ),
                "understands_no_automatic_changes": (
                    body.understands_no_automatic_changes
                ),
            },
        )
    except (GovernedAIProviderConnectionError, CostEconomicsError) as exc:
        raise _http_error(exc) from exc
    return envelope(request, data)


@router.get("/{connection_id}/standby")
def get_governed_ai_provider_standby(
    request: Request,
    connection_id: str,
    user: dict = Depends(require_org_role({"org_owner"})),
    db: Session = Depends(get_db),
) -> dict:
    try:
        data = list_provider_standby_events(
            db,
            organization_id=str(user["organization_id"]),
            connection_id=connection_id,
        )
    except GovernedAIProviderConnectionError as exc:
        raise _http_error(exc) from exc
    return envelope(request, data)


@router.put("/{connection_id}/standby")
def update_governed_ai_provider_standby(
    request: Request,
    connection_id: str,
    body: GovernedAIProviderStandbyIn,
    user: dict = Depends(require_org_role({"org_owner"})),
    db: Session = Depends(get_db),
) -> dict:
    try:
        data = set_provider_standby(
            db,
            organization_id=str(user["organization_id"]),
            connection_id=connection_id,
            actor_user_id=str(user["id"]),
            action=body.action,
            client_request_id=body.client_request_id,
            review_id=body.review_id,
            acknowledgements={
                "reviewed_standby_boundary": body.reviewed_standby_boundary,
                "understands_zero_customer_prompts": (
                    body.understands_zero_customer_prompts
                ),
                "understands_managed_route_unchanged": (
                    body.understands_managed_route_unchanged
                ),
                "understands_manual_disable_available": (
                    body.understands_manual_disable_available
                ),
            },
        )
    except (GovernedAIProviderConnectionError, CostEconomicsError) as exc:
        raise _http_error(exc) from exc
    return envelope(request, data)


@router.get("/{connection_id}/routing-readiness")
def get_governed_ai_provider_routing_readiness(
    request: Request,
    connection_id: str,
    user: dict = Depends(require_org_role({"org_owner"})),
    db: Session = Depends(get_db),
) -> dict:
    try:
        data = list_provider_routing_readiness(
            db,
            organization_id=str(user["organization_id"]),
            connection_id=connection_id,
        )
    except GovernedAIProviderConnectionError as exc:
        raise _http_error(exc) from exc
    return envelope(request, data)


@router.post("/{connection_id}/routing-readiness")
def check_governed_ai_provider_routing_readiness(
    request: Request,
    connection_id: str,
    body: GovernedAIProviderReadinessIn,
    user: dict = Depends(require_org_role({"org_owner"})),
    db: Session = Depends(get_db),
) -> dict:
    try:
        data = check_provider_routing_readiness(
            db,
            organization_id=str(user["organization_id"]),
            connection_id=connection_id,
            actor_user_id=str(user["id"]),
            client_request_id=body.client_request_id,
        )
    except (GovernedAIProviderConnectionError, CostEconomicsError) as exc:
        raise _http_error(exc) from exc
    return envelope(request, data)


@router.get("/{connection_id}/routing-canary")
def get_governed_ai_provider_routing_canary(
    request: Request,
    connection_id: str,
    user: dict = Depends(require_org_role({"org_owner"})),
    db: Session = Depends(get_db),
) -> dict:
    try:
        data = list_provider_canary(
            db,
            organization_id=str(user["organization_id"]),
            connection_id=connection_id,
        )
    except GovernedAIProviderConnectionError as exc:
        raise _http_error(exc) from exc
    return envelope(request, data)


@router.put("/{connection_id}/routing-canary")
def update_governed_ai_provider_routing_canary(
    request: Request,
    connection_id: str,
    body: GovernedAIProviderCanaryIn,
    user: dict = Depends(require_org_role({"org_owner"})),
    db: Session = Depends(get_db),
) -> dict:
    try:
        data = set_provider_canary(
            db,
            organization_id=str(user["organization_id"]),
            connection_id=connection_id,
            actor_user_id=str(user["id"]),
            action=body.action,
            client_request_id=body.client_request_id,
            acknowledgements={
                "reviewed_five_percent_limit": body.reviewed_five_percent_limit,
                "understands_real_customer_prompt": (
                    body.understands_real_customer_prompt
                ),
                "understands_managed_fallback_required": (
                    body.understands_managed_fallback_required
                ),
                "understands_automatic_rollback": (
                    body.understands_automatic_rollback
                ),
                "understands_no_automatic_changes": (
                    body.understands_no_automatic_changes
                ),
            },
        )
    except (GovernedAIProviderConnectionError, CostEconomicsError) as exc:
        raise _http_error(exc) from exc
    return envelope(request, data)


@router.get("/{connection_id}/routing-canary-monitoring")
def get_governed_ai_provider_routing_canary_monitoring(
    request: Request,
    connection_id: str,
    user: dict = Depends(require_org_role({"org_owner"})),
    db: Session = Depends(get_db),
) -> dict:
    try:
        data = list_canary_monitoring(
            db,
            organization_id=str(user["organization_id"]),
            connection_id=connection_id,
        )
    except GovernedAIProviderConnectionError as exc:
        raise _http_error(exc) from exc
    return envelope(request, data)


@router.post("/{connection_id}/routing-canary-monitoring")
def create_governed_ai_provider_routing_canary_monitoring(
    request: Request,
    connection_id: str,
    body: GovernedAIProviderCanaryMonitoringIn,
    user: dict = Depends(require_org_role({"org_owner"})),
    db: Session = Depends(get_db),
) -> dict:
    try:
        data = create_canary_monitoring_snapshot(
            db,
            organization_id=str(user["organization_id"]),
            connection_id=connection_id,
            actor_user_id=str(user["id"]),
            client_request_id=body.client_request_id,
        )
    except (GovernedAIProviderConnectionError, CostEconomicsError) as exc:
        raise _http_error(exc) from exc
    return envelope(request, data)


@router.get("/{connection_id}/question-capability")
def get_governed_ai_provider_question_capability(
    request: Request,
    connection_id: str,
    user: dict = Depends(require_org_role({"org_owner"})),
    db: Session = Depends(get_db),
) -> dict:
    try:
        data = list_question_capability(
            db,
            organization_id=str(user["organization_id"]),
            connection_id=connection_id,
        )
    except (GovernedAIProviderConnectionError, CostEconomicsError) as exc:
        raise _http_error(exc) from exc
    return envelope(request, data)


@router.post("/{connection_id}/question-capability/benchmark")
def benchmark_governed_ai_provider_question_capability(
    request: Request,
    connection_id: str,
    body: GovernedAIProviderCanaryMonitoringIn,
    user: dict = Depends(require_org_role({"org_owner"})),
    db: Session = Depends(get_db),
) -> dict:
    try:
        data = run_question_capability_benchmark(
            db,
            organization_id=str(user["organization_id"]),
            connection_id=connection_id,
            actor_user_id=str(user["id"]),
            client_request_id=body.client_request_id,
        )
    except (GovernedAIProviderConnectionError, CostEconomicsError) as exc:
        raise _http_error(exc) from exc
    return envelope(request, data)


@router.put("/{connection_id}/question-capability")
def update_governed_ai_provider_question_capability(
    request: Request,
    connection_id: str,
    body: GovernedAIProviderQuestionCapabilityIn,
    user: dict = Depends(require_org_role({"org_owner"})),
    db: Session = Depends(get_db),
) -> dict:
    try:
        data = set_question_capability(
            db,
            organization_id=str(user["organization_id"]),
            connection_id=connection_id,
            actor_user_id=str(user["id"]),
            action=body.action,
            client_request_id=body.client_request_id,
            acknowledgements={
                "reviewed_question_capability_check": (
                    body.reviewed_question_capability_check
                ),
                "understands_real_customer_questions": (
                    body.understands_real_customer_questions
                ),
                "understands_shared_daily_limit": body.understands_shared_daily_limit,
                "understands_managed_fallback_and_rollback": (
                    body.understands_managed_fallback_and_rollback
                ),
                "understands_no_automatic_changes": (
                    body.understands_no_automatic_changes
                ),
            },
        )
    except (GovernedAIProviderConnectionError, CostEconomicsError) as exc:
        raise _http_error(exc) from exc
    return envelope(request, data)


def _http_error(
    exc: GovernedAIProviderConnectionError | CostEconomicsError,
) -> HTTPException:
    return HTTPException(
        status_code=int(getattr(exc, "status_code", 409)),
        detail={
            "message": str(exc),
            "reason_code": str(getattr(exc, "reason_code", "ai_provider_unavailable")),
        },
    )

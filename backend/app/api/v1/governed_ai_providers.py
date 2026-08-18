from __future__ import annotations

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


router = APIRouter(prefix="/ai/providers", tags=["governed-ai-providers"])


class GovernedAIProviderConnectionIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    endpoint_url: str = Field(min_length=10, max_length=2_000)
    model_identifier: str = Field(min_length=1, max_length=200)
    api_key: str | None = Field(default=None, max_length=4_096)


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

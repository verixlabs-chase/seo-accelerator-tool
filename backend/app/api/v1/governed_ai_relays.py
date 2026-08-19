from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import re
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.deps import require_org_role
from app.api.response import envelope
from app.db.session import get_db, set_session_security_context
from app.services.commercial_plan_service import (
    FEATURE_PRIVATE_AI_PROVIDER,
    require_commercial_feature,
)
from app.services.governed_ai_relay_service import (
    GovernedAIRelayError,
    acknowledge_relay_diagnostic_packet,
    create_relay_diagnostic_packet,
    create_relay_enrollment,
    list_relay_enrollments,
    record_relay_heartbeat,
    record_relay_model_qualification,
    record_relay_runtime_discovery,
    revoke_relay_enrollment,
)
from app.services.cost_economics_service import CostEconomicsError


tenant_router = APIRouter(prefix="/ai/relay-enrollments", tags=["governed-ai-relay"])
public_router = APIRouter(prefix="/ai/relay", tags=["governed-ai-relay"])
_BEARER_PATTERN = re.compile(r"^Bearer\s+(.+)$", re.IGNORECASE)
_RELAY_AGENT_PATH = (
    Path(__file__).resolve().parents[2]
    / "customer_relay"
    / "insightos_local_relay.py"
)


class GovernedAIRelayEnrollmentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=120)
    client_request_id: str = Field(min_length=8, max_length=128)
    understands_connection_only: bool = False
    understands_no_customer_prompts: bool = False
    understands_no_database_or_execution_access: bool = False
    understands_manual_revocation: bool = False


class GovernedAIRelayDiagnosticIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_request_id: str = Field(min_length=8, max_length=128)


class GovernedAIRelayDiagnosticAcknowledgementIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    packet_artifact_hash: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    response_hash: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    signature: str = Field(pattern=r"^[0-9a-fA-F]{64}$")


class GovernedAIRelayRuntimeDiscoveryIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    discovery_id: str = Field(min_length=36, max_length=36)
    agent_version: str = Field(min_length=1, max_length=30)
    runtime_kind: Literal["not_found", "ollama", "lm_studio", "multiple"]
    model_count: int = Field(ge=0, le=1000)
    ollama_detected: bool
    lm_studio_detected: bool
    loopback_only: bool
    customer_data_sent: bool
    model_called: bool
    model_identifiers_included: bool
    observed_at: datetime
    signature: str = Field(pattern=r"^[0-9a-fA-F]{64}$")


class GovernedAIRelayModelQualificationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    qualification_id: str = Field(min_length=36, max_length=36)
    agent_version: str = Field(min_length=1, max_length=30)
    runtime_kind: Literal["ollama", "lm_studio"]
    local_model_fingerprint: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    prompt_version: Literal["local-model-synthetic-v1"]
    status: Literal["passed", "failed"]
    latency_ms: int = Field(ge=0, le=120000)
    output_json_valid: bool
    required_contract_matched: bool
    synthetic_input_only: bool
    model_call_attempted: bool
    model_response_received: bool
    customer_data_sent: bool
    raw_model_identifier_sent: bool
    model_output_sent: bool
    customer_work_allowed: bool
    publishing_allowed: bool
    observed_at: datetime
    signature: str = Field(pattern=r"^[0-9a-fA-F]{64}$")


@tenant_router.get("")
def get_governed_ai_relay_enrollments(
    request: Request,
    user: dict = Depends(require_org_role({"org_owner"})),
    db: Session = Depends(get_db),
) -> dict:
    data = list_relay_enrollments(
        db,
        organization_id=str(user["organization_id"]),
    )
    return envelope(request, data)


@tenant_router.get("/agent/download", response_class=Response)
def download_governed_ai_local_relay_agent(
    user: dict = Depends(require_org_role({"org_owner"})),
    db: Session = Depends(get_db),
) -> Response:
    try:
        require_commercial_feature(
            db,
            organization_id=str(user["organization_id"]),
            feature_code=FEATURE_PRIVATE_AI_PROVIDER,
        )
    except CostEconomicsError as exc:
        raise _http_error(exc) from exc
    source = _RELAY_AGENT_PATH.read_bytes()
    return Response(
        content=source,
        media_type="text/x-python; charset=utf-8",
        headers={
            "Content-Disposition": (
                'attachment; filename="insightos-local-relay.py"'
            ),
            "X-Content-SHA256": sha256(source).hexdigest(),
            "Cache-Control": "no-store",
        },
    )


@tenant_router.post("", status_code=status.HTTP_201_CREATED)
def create_governed_ai_relay_enrollment(
    request: Request,
    body: GovernedAIRelayEnrollmentIn,
    user: dict = Depends(require_org_role({"org_owner"})),
    db: Session = Depends(get_db),
) -> dict:
    try:
        data = create_relay_enrollment(
            db,
            organization_id=str(user["organization_id"]),
            actor_user_id=str(user["id"]),
            name=body.name,
            client_request_id=body.client_request_id,
            acknowledgements={
                "understands_connection_only": body.understands_connection_only,
                "understands_no_customer_prompts": (
                    body.understands_no_customer_prompts
                ),
                "understands_no_database_or_execution_access": (
                    body.understands_no_database_or_execution_access
                ),
                "understands_manual_revocation": body.understands_manual_revocation,
            },
        )
    except (GovernedAIRelayError, CostEconomicsError) as exc:
        raise _http_error(exc) from exc
    return envelope(request, data)


@tenant_router.delete("/{enrollment_id}")
def delete_governed_ai_relay_enrollment(
    request: Request,
    enrollment_id: str,
    user: dict = Depends(require_org_role({"org_owner"})),
    db: Session = Depends(get_db),
) -> dict:
    try:
        data = revoke_relay_enrollment(
            db,
            organization_id=str(user["organization_id"]),
            enrollment_id=enrollment_id,
            actor_user_id=str(user["id"]),
        )
    except GovernedAIRelayError as exc:
        raise _http_error(exc) from exc
    return envelope(request, data)


@tenant_router.post(
    "/{enrollment_id}/diagnostic-packets",
    status_code=status.HTTP_201_CREATED,
)
def create_governed_ai_relay_diagnostic_packet(
    request: Request,
    enrollment_id: str,
    body: GovernedAIRelayDiagnosticIn,
    user: dict = Depends(require_org_role({"org_owner"})),
    db: Session = Depends(get_db),
) -> dict:
    try:
        data = create_relay_diagnostic_packet(
            db,
            organization_id=str(user["organization_id"]),
            enrollment_id=enrollment_id,
            actor_user_id=str(user["id"]),
            client_request_id=body.client_request_id,
        )
    except (GovernedAIRelayError, CostEconomicsError) as exc:
        raise _http_error(exc) from exc
    return envelope(request, data)


@public_router.post("/heartbeat")
def post_governed_ai_relay_heartbeat(
    request: Request,
    authorization: str = Header(default="", alias="Authorization"),
    db: Session = Depends(get_db),
) -> dict:
    bearer_token = _bearer_token(authorization)
    set_session_security_context(
        db,
        tenant_id=None,
        organization_id=None,
        user_id="governed-ai-local-relay",
        platform_access=True,
    )
    try:
        data = record_relay_heartbeat(db, bearer_token=bearer_token)
    except GovernedAIRelayError as exc:
        raise _http_error(exc) from exc
    return envelope(request, data)


@public_router.post("/runtime-discovery")
def post_governed_ai_relay_runtime_discovery(
    request: Request,
    body: GovernedAIRelayRuntimeDiscoveryIn,
    authorization: str = Header(default="", alias="Authorization"),
    db: Session = Depends(get_db),
) -> dict:
    bearer_token = _bearer_token(authorization)
    set_session_security_context(
        db,
        tenant_id=None,
        organization_id=None,
        user_id="governed-ai-local-relay",
        platform_access=True,
    )
    try:
        data = record_relay_runtime_discovery(
            db,
            bearer_token=bearer_token,
            discovery_id=body.discovery_id,
            agent_version=body.agent_version,
            runtime_kind=body.runtime_kind,
            model_count=body.model_count,
            ollama_detected=body.ollama_detected,
            lm_studio_detected=body.lm_studio_detected,
            loopback_only=body.loopback_only,
            customer_data_sent=body.customer_data_sent,
            model_called=body.model_called,
            model_identifiers_included=body.model_identifiers_included,
            observed_at=body.observed_at,
            signature=body.signature,
        )
    except GovernedAIRelayError as exc:
        raise _http_error(exc) from exc
    return envelope(request, data)


@public_router.post("/model-qualification")
def post_governed_ai_relay_model_qualification(
    request: Request,
    body: GovernedAIRelayModelQualificationIn,
    authorization: str = Header(default="", alias="Authorization"),
    db: Session = Depends(get_db),
) -> dict:
    bearer_token = _bearer_token(authorization)
    set_session_security_context(
        db,
        tenant_id=None,
        organization_id=None,
        user_id="governed-ai-local-relay",
        platform_access=True,
    )
    try:
        data = record_relay_model_qualification(
            db,
            bearer_token=bearer_token,
            qualification_id=body.qualification_id,
            agent_version=body.agent_version,
            runtime_kind=body.runtime_kind,
            local_model_fingerprint=body.local_model_fingerprint,
            prompt_version=body.prompt_version,
            status=body.status,
            latency_ms=body.latency_ms,
            output_json_valid=body.output_json_valid,
            required_contract_matched=body.required_contract_matched,
            synthetic_input_only=body.synthetic_input_only,
            model_call_attempted=body.model_call_attempted,
            model_response_received=body.model_response_received,
            customer_data_sent=body.customer_data_sent,
            raw_model_identifier_sent=body.raw_model_identifier_sent,
            model_output_sent=body.model_output_sent,
            customer_work_allowed=body.customer_work_allowed,
            publishing_allowed=body.publishing_allowed,
            observed_at=body.observed_at,
            signature=body.signature,
        )
    except GovernedAIRelayError as exc:
        raise _http_error(exc) from exc
    return envelope(request, data)


@public_router.post("/packets/{packet_id}/acknowledge")
def post_governed_ai_relay_diagnostic_acknowledgement(
    request: Request,
    packet_id: str,
    body: GovernedAIRelayDiagnosticAcknowledgementIn,
    authorization: str = Header(default="", alias="Authorization"),
    db: Session = Depends(get_db),
) -> dict:
    bearer_token = _bearer_token(authorization)
    set_session_security_context(
        db,
        tenant_id=None,
        organization_id=None,
        user_id="governed-ai-local-relay",
        platform_access=True,
    )
    try:
        data = acknowledge_relay_diagnostic_packet(
            db,
            bearer_token=bearer_token,
            packet_id=packet_id,
            packet_artifact_hash=body.packet_artifact_hash,
            response_hash=body.response_hash,
            signature=body.signature,
        )
    except GovernedAIRelayError as exc:
        raise _http_error(exc) from exc
    return envelope(request, data)


def _bearer_token(authorization: str) -> str:
    match = _BEARER_PATTERN.match(authorization.strip())
    if match is None or not match.group(1).strip():
        raise HTTPException(
            status_code=401,
            detail={
                "message": "A local relay connection key is required.",
                "reason_code": "relay_token_required",
            },
        )
    return match.group(1).strip()


def _http_error(exc: GovernedAIRelayError | CostEconomicsError) -> HTTPException:
    return HTTPException(
        status_code=getattr(exc, "status_code", 409),
        detail={
            "message": str(exc),
            "reason_code": getattr(exc, "reason_code", "relay_unavailable"),
        },
    )

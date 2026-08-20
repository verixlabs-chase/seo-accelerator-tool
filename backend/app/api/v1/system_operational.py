from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import require_platform_owner, require_platform_role
from app.api.response import envelope
from app.db.session import get_db
from app.services import freshness_monitor_service, infra_service, job_service
from app.services.launch_readiness_service import (
    LaunchReadinessProofError,
    build_launch_readiness,
    create_launch_readiness_decision,
    create_launch_readiness_proof,
    serialize_launch_readiness_decision,
    serialize_launch_readiness_proof,
)
from app.services.operational_telemetry_service import snapshot_operational_health


router = APIRouter(tags=["ops"])


class LaunchReadinessProofIn(BaseModel):
    gate_code: Literal[
        "critical_journeys",
        "recovery_drills",
        "customer_communications",
        "first_use_comprehension",
        "known_limitations",
    ]
    result: Literal["passed", "failed"]
    proof_kind: Literal[
        "production_smoke",
        "recovery_drill",
        "communication_test",
        "moderated_test",
        "capability_review",
    ]
    summary: str = Field(min_length=20, max_length=300)
    evidence_reference: str = Field(min_length=8, max_length=160)
    observed_at: datetime
    expires_at: datetime


class LaunchReadinessDecisionIn(BaseModel):
    decision: Literal["go", "no_go"]
    release_reference: str = Field(min_length=8, max_length=120)
    rationale: str = Field(min_length=20, max_length=500)
    known_limitations_acknowledged: bool
    support_owner_confirmed: bool
    rollback_owner_confirmed: bool
    evidence_current_confirmed: bool


@router.get("/system/operational-health")
def system_operational_health(
    request: Request,
    db: Session = Depends(get_db),
    _user: dict = Depends(require_platform_role({"platform_owner", "platform_admin"})),
) -> dict:
    queue_status = infra_service.celery_queue_status()
    for queue_name in queue_status["active_queues"]:
        infra_service.queue_depth_count(str(queue_name))

    payload = snapshot_operational_health()
    payload["active_queues"] = list(queue_status["active_queues"])
    payload["worker_count_per_queue"] = dict(queue_status["worker_count_per_queue"])
    payload["data_freshness"] = freshness_monitor_service.get_data_freshness_summary(db)
    payload["durable_jobs"] = job_service.durable_job_health(db)
    return envelope(request, {"operational_health": payload})


@router.get("/system/data-freshness")
def system_data_freshness(
    request: Request,
    db: Session = Depends(get_db),
    _user: dict = Depends(require_platform_role({"platform_owner", "platform_admin"})),
) -> dict:
    return envelope(request, freshness_monitor_service.get_data_freshness_summary(db))


@router.get("/system/launch-readiness")
def system_launch_readiness(
    request: Request,
    db: Session = Depends(get_db),
    _user: dict = Depends(require_platform_role({"platform_owner", "platform_admin"})),
) -> dict:
    return envelope(request, build_launch_readiness(db))


@router.post("/system/launch-readiness/proofs")
def record_system_launch_readiness_proof(
    request: Request,
    body: LaunchReadinessProofIn,
    db: Session = Depends(get_db),
    user: dict = Depends(require_platform_owner()),
) -> dict:
    try:
        proof, created = create_launch_readiness_proof(
            db,
            gate_code=body.gate_code,
            result=body.result,
            proof_kind=body.proof_kind,
            summary=body.summary,
            evidence_reference=body.evidence_reference,
            observed_at=body.observed_at,
            expires_at=body.expires_at,
            recorded_by_user_id=user["id"],
        )
        db.commit()
        db.refresh(proof)
    except LaunchReadinessProofError as exc:
        db.rollback()
        raise HTTPException(
            status_code=exc.status_code,
            detail={"message": str(exc), "reason_code": exc.reason_code},
        ) from exc
    return envelope(
        request,
        {
            "created": created,
            "proof": serialize_launch_readiness_proof(proof),
            "readiness": build_launch_readiness(db),
        },
    )


@router.post("/system/launch-readiness/decisions")
def record_system_launch_readiness_decision(
    request: Request,
    body: LaunchReadinessDecisionIn,
    db: Session = Depends(get_db),
    user: dict = Depends(require_platform_owner()),
) -> dict:
    try:
        decision, created = create_launch_readiness_decision(
            db,
            decision=body.decision,
            release_reference=body.release_reference,
            rationale=body.rationale,
            known_limitations_acknowledged=body.known_limitations_acknowledged,
            support_owner_confirmed=body.support_owner_confirmed,
            rollback_owner_confirmed=body.rollback_owner_confirmed,
            evidence_current_confirmed=body.evidence_current_confirmed,
            decided_by_user_id=user["id"],
        )
        db.commit()
        db.refresh(decision)
        readiness = build_launch_readiness(db)
    except LaunchReadinessProofError as exc:
        db.rollback()
        raise HTTPException(
            status_code=exc.status_code,
            detail={"message": str(exc), "reason_code": exc.reason_code},
        ) from exc
    return envelope(
        request,
        {
            "created": created,
            "decision": serialize_launch_readiness_decision(
                decision,
                basis_digest=readiness["basis_digest"],
            ),
            "readiness": readiness,
        },
    )

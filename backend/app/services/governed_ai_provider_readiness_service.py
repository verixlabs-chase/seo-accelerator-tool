from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from hashlib import sha256

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.models.governed_ai import GovernedAIRun
from app.models.governed_ai_provider_connection import GovernedAIProviderConnection
from app.models.governed_ai_provider_routing_readiness import (
    GovernedAIProviderRoutingReadiness,
)
from app.models.organization import Organization
from app.services.audit_service import write_audit_log
from app.services.commercial_plan_service import (
    FEATURE_PRIVATE_AI_PROVIDER,
    require_commercial_feature,
)
from app.services.governed_ai_provider_connection_service import (
    GovernedAIProviderConnectionError,
)
from app.services.governed_ai_provider_standby_service import (
    current_provider_standby_event,
)


READINESS_VERSION = "managed-fallback-readiness-v1"
MANAGED_EVIDENCE_MAX_AGE = timedelta(hours=24)
USAGE_WINDOW = timedelta(days=30)


def list_provider_routing_readiness(
    db: Session,
    *,
    organization_id: str,
    connection_id: str,
) -> dict[str, object]:
    connection = (
        db.query(GovernedAIProviderConnection)
        .filter(
            GovernedAIProviderConnection.id == connection_id,
            GovernedAIProviderConnection.organization_id == organization_id,
        )
        .one_or_none()
    )
    if connection is None:
        raise GovernedAIProviderConnectionError(
            "Private AI provider not found.",
            reason_code="ai_provider_connection_not_found",
            status_code=404,
        )
    rows = (
        db.query(GovernedAIProviderRoutingReadiness)
        .filter(
            GovernedAIProviderRoutingReadiness.organization_id == organization_id,
            GovernedAIProviderRoutingReadiness.connection_id == connection_id,
        )
        .order_by(
            GovernedAIProviderRoutingReadiness.created_at.desc(),
            GovernedAIProviderRoutingReadiness.id.desc(),
        )
        .all()
    )
    latest = _serialize(rows[0]) if rows else None
    return {
        "items": [_serialize(row) for row in rows],
        "count": len(rows),
        "latest": latest,
        "truth": _truth(latest),
        "routing_enabled": False,
        "traffic_percentage": 0,
        "customer_prompts_allowed": False,
        "automatic_changes_allowed": False,
    }


def check_provider_routing_readiness(
    db: Session,
    *,
    organization_id: str,
    connection_id: str,
    actor_user_id: str,
    client_request_id: str,
    now_provider: Callable[[], datetime] = lambda: datetime.now(UTC),
    settings_provider: Callable[[], object] = get_settings,
) -> dict[str, object]:
    require_commercial_feature(
        db,
        organization_id=organization_id,
        feature_code=FEATURE_PRIVATE_AI_PROVIDER,
    )
    idempotency_key = client_request_id.strip()
    if len(idempotency_key) < 8 or len(idempotency_key) > 64:
        raise GovernedAIProviderConnectionError(
            "The readiness request identifier is invalid.",
            reason_code="ai_provider_readiness_request_invalid",
            status_code=422,
        )
    existing = _find_existing(
        db,
        organization_id=organization_id,
        connection_id=connection_id,
        idempotency_key=idempotency_key,
    )
    if existing is not None:
        return _result(existing, created=False)

    organization = (
        db.query(Organization)
        .filter(Organization.id == organization_id)
        .with_for_update()
        .one_or_none()
    )
    if organization is None:
        raise GovernedAIProviderConnectionError(
            "Organization not found.",
            reason_code="organization_not_found",
            status_code=404,
        )
    connection = (
        db.query(GovernedAIProviderConnection)
        .filter(
            GovernedAIProviderConnection.id == connection_id,
            GovernedAIProviderConnection.organization_id == organization_id,
            GovernedAIProviderConnection.status == "candidate",
        )
        .with_for_update()
        .one_or_none()
    )
    if connection is None:
        raise GovernedAIProviderConnectionError(
            "Private AI provider not found.",
            reason_code="ai_provider_connection_not_found",
            status_code=404,
        )
    existing = _find_existing(
        db,
        organization_id=organization_id,
        connection_id=connection_id,
        idempotency_key=idempotency_key,
    )
    if existing is not None:
        return _result(existing, created=False)
    standby = current_provider_standby_event(
        db,
        organization_id=organization_id,
        connection=connection,
    )
    if standby is None:
        raise GovernedAIProviderConnectionError(
            "Register this provider in zero-traffic standby before checking routing safety.",
            reason_code="ai_provider_readiness_standby_required",
            status_code=409,
        )

    now = _as_utc(now_provider())
    settings = settings_provider()
    managed_configured = bool(
        str(getattr(settings, "ai_provider_backend", "")).strip().lower()
        == "mistral"
        and str(getattr(settings, "mistral_api_key", "")).strip()
    )
    latest_run = (
        db.query(GovernedAIRun)
        .filter(
            GovernedAIRun.organization_id == organization_id,
            GovernedAIRun.provider_name == "mistral",
        )
        .order_by(GovernedAIRun.created_at.desc(), GovernedAIRun.id.desc())
        .first()
    )
    blockers: list[dict[str, str]] = []
    managed_route_status = "unavailable"
    managed_evidence_at: datetime | None = None
    managed_evidence_hash: str | None = None
    if not managed_configured:
        managed_route_status = "not_configured"
        blockers.append(
            {
                "code": "managed_route_not_configured",
                "summary": "The managed AI fallback is not configured.",
            }
        )
    elif latest_run is None:
        blockers.append(
            {
                "code": "managed_route_evidence_missing",
                "summary": "No recent saved managed-AI result is available yet.",
            }
        )
    else:
        managed_evidence_at = _as_utc(latest_run.completed_at or latest_run.created_at)
        managed_evidence_hash = _hash(
            {
                "run_id": latest_run.id,
                "status": latest_run.status,
                "provider_state": latest_run.provider_state,
                "completed_at": managed_evidence_at.isoformat(),
            }
        )
        if latest_run.status != "validated" or latest_run.completed_at is None:
            blockers.append(
                {
                    "code": "managed_route_latest_result_not_successful",
                    "summary": "The latest managed-AI result did not finish successfully.",
                }
            )
        elif now - managed_evidence_at > MANAGED_EVIDENCE_MAX_AGE:
            managed_route_status = "stale"
            blockers.append(
                {
                    "code": "managed_route_evidence_stale",
                    "summary": "The latest managed-AI success is more than 24 hours old.",
                }
            )
        else:
            managed_route_status = "healthy"

    usage_rows = (
        db.query(GovernedAIRun)
        .filter(
            GovernedAIRun.organization_id == organization_id,
            GovernedAIRun.provider_name == "mistral",
            GovernedAIRun.created_at >= now - USAGE_WINDOW,
        )
        .all()
    )
    managed_run_count = len(usage_rows)
    managed_validated_count = sum(1 for row in usage_rows if row.status == "validated")
    managed_fallback_count = sum(
        1 for row in usage_rows if row.status in {"fallback", "failed", "rejected"}
    )
    managed_input_tokens = sum(max(0, int(row.input_tokens or 0)) for row in usage_rows)
    managed_output_tokens = sum(max(0, int(row.output_tokens or 0)) for row in usage_rows)
    status = "passed" if not blockers and managed_route_status == "healthy" else "blocked"
    rollback_ready = status == "passed"
    artifact = {
        "tenant_id": organization_id,
        "organization_id": organization_id,
        "connection_id": connection_id,
        "standby_event_id": standby.id,
        "readiness_version": READINESS_VERSION,
        "status": status,
        "managed_backend": "mistral",
        "managed_route_status": managed_route_status,
        "managed_evidence_hash": managed_evidence_hash,
        "managed_evidence_at": (
            managed_evidence_at.isoformat() if managed_evidence_at else None
        ),
        "standby_evidence_current": True,
        "rollback_ready": rollback_ready,
        "blockers": blockers,
        "usage_window_days": 30,
        "managed_run_count": managed_run_count,
        "managed_validated_count": managed_validated_count,
        "managed_fallback_count": managed_fallback_count,
        "managed_input_tokens": managed_input_tokens,
        "managed_output_tokens": managed_output_tokens,
        "candidate_run_count": 0,
        "traffic_percentage": 0,
        "routing_enabled": False,
        "customer_prompts_allowed": False,
        "automatic_changes_allowed": False,
        "automatic_activation_allowed": False,
        "idempotency_key": idempotency_key,
    }
    row = GovernedAIProviderRoutingReadiness(
        tenant_id=organization_id,
        organization_id=organization_id,
        connection_id=connection_id,
        standby_event_id=standby.id,
        readiness_version=READINESS_VERSION,
        status=status,
        managed_backend="mistral",
        managed_route_status=managed_route_status,
        managed_evidence_hash=managed_evidence_hash,
        managed_evidence_at=managed_evidence_at,
        standby_evidence_current=True,
        rollback_ready=rollback_ready,
        blockers=blockers,
        usage_window_days=30,
        managed_run_count=managed_run_count,
        managed_validated_count=managed_validated_count,
        managed_fallback_count=managed_fallback_count,
        managed_input_tokens=managed_input_tokens,
        managed_output_tokens=managed_output_tokens,
        candidate_run_count=0,
        traffic_percentage=0,
        routing_enabled=False,
        customer_prompts_allowed=False,
        automatic_changes_allowed=False,
        automatic_activation_allowed=False,
        artifact_hash=_hash(artifact),
        idempotency_key=idempotency_key,
        created_by_user_id=actor_user_id,
        created_at=now,
    )
    db.add(row)
    write_audit_log(
        db,
        tenant_id=organization_id,
        actor_user_id=actor_user_id,
        event_type=f"ai.provider_routing_readiness.{status}",
        payload={
            "readiness_id": row.id,
            "connection_id": connection_id,
            "status": status,
            "managed_route_status": managed_route_status,
            "standby_evidence_current": True,
            "rollback_ready": rollback_ready,
            "traffic_percentage": 0,
            "routing_enabled": False,
            "customer_prompts_allowed": False,
            "automatic_changes_allowed": False,
        },
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = _find_existing(
            db,
            organization_id=organization_id,
            connection_id=connection_id,
            idempotency_key=idempotency_key,
        )
        if existing is None:
            raise
        return _result(existing, created=False)
    db.refresh(row)
    return _result(row, created=True)


def _find_existing(
    db: Session,
    *,
    organization_id: str,
    connection_id: str,
    idempotency_key: str,
) -> GovernedAIProviderRoutingReadiness | None:
    return (
        db.query(GovernedAIProviderRoutingReadiness)
        .filter(
            GovernedAIProviderRoutingReadiness.organization_id == organization_id,
            GovernedAIProviderRoutingReadiness.connection_id == connection_id,
            GovernedAIProviderRoutingReadiness.idempotency_key == idempotency_key,
        )
        .one_or_none()
    )


def _serialize(row: GovernedAIProviderRoutingReadiness) -> dict[str, object]:
    return {
        "id": row.id,
        "connection_id": row.connection_id,
        "status": row.status,
        "managed_route_status": row.managed_route_status,
        "managed_evidence_at": (
            row.managed_evidence_at.isoformat() if row.managed_evidence_at else None
        ),
        "standby_evidence_current": row.standby_evidence_current,
        "rollback_ready": row.rollback_ready,
        "blockers": row.blockers,
        "usage": {
            "window_days": 30,
            "managed_runs": row.managed_run_count,
            "managed_successes": row.managed_validated_count,
            "managed_fallbacks": row.managed_fallback_count,
            "managed_input_tokens": row.managed_input_tokens,
            "managed_output_tokens": row.managed_output_tokens,
            "candidate_runs": 0,
        },
        "traffic_percentage": 0,
        "routing_enabled": False,
        "customer_prompts_allowed": False,
        "automatic_changes_allowed": False,
        "automatic_activation_allowed": False,
        "created_at": row.created_at.isoformat(),
        "immutable": True,
    }


def _truth(item: dict[str, object] | None) -> dict[str, str]:
    if item is None:
        return {
            "state": "not_checked",
            "summary": "Fallback readiness has not been checked yet.",
        }
    if item["status"] == "passed":
        return {
            "state": "ready_for_later_routing_review",
            "summary": (
                "The managed fallback has a recent successful result and the private "
                "provider still has zero traffic. A separate routing approval is still required."
            ),
        }
    return {
        "state": "needs_attention",
        "summary": (
            "The routing safety prerequisites are incomplete. No customer prompts were "
            "sent to the private provider."
        ),
    }


def _result(
    row: GovernedAIProviderRoutingReadiness,
    *,
    created: bool,
) -> dict[str, object]:
    item = _serialize(row)
    return {
        "created": created,
        "item": item,
        "truth": _truth(item),
        "routing_enabled": False,
        "traffic_percentage": 0,
        "customer_prompts_allowed": False,
        "automatic_changes_allowed": False,
    }


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _hash(payload: dict[str, object]) -> str:
    return sha256(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()

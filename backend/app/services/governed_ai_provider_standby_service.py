from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from hashlib import sha256
from typing import Callable

from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.models.governed_ai_provider_benchmark import GovernedAIProviderBenchmark
from app.models.governed_ai_provider_connection import GovernedAIProviderConnection
from app.models.governed_ai_provider_review import GovernedAIProviderReview
from app.models.governed_ai_provider_standby_event import (
    GovernedAIProviderStandbyEvent,
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
from app.services.governed_ai_provider_review_service import (
    provider_review_artifact_is_valid,
    require_exact_passing_evidence,
)


STANDBY_ACKNOWLEDGEMENTS = (
    "reviewed_standby_boundary",
    "understands_zero_customer_prompts",
    "understands_managed_route_unchanged",
    "understands_manual_disable_available",
)
_CLIENT_REQUEST_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,63}$")


def list_provider_standby_events(
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
        db.query(GovernedAIProviderStandbyEvent)
        .filter(
            GovernedAIProviderStandbyEvent.organization_id == organization_id,
            GovernedAIProviderStandbyEvent.connection_id == connection_id,
        )
        .order_by(
            GovernedAIProviderStandbyEvent.created_at.desc(),
            GovernedAIProviderStandbyEvent.id.desc(),
        )
        .all()
    )
    current = _current_state(
        db,
        organization_id=organization_id,
        connection=connection,
    )
    return {
        "items": [_serialize(row) for row in rows],
        "count": len(rows),
        "current": current,
        "truth": {
            "state": current["state"],
            "summary": current["summary"],
        },
        "managed_route": "mistral",
        "routing_enabled": False,
        "traffic_percentage": 0,
        "customer_prompts_allowed": False,
        "automatic_changes_allowed": False,
    }


def set_provider_standby(
    db: Session,
    *,
    organization_id: str,
    connection_id: str,
    actor_user_id: str,
    action: str,
    client_request_id: str,
    review_id: str | None,
    acknowledgements: dict[str, bool],
    settings_provider: Callable[[], object] = get_settings,
) -> dict[str, object]:
    if action not in {"enable", "disable"}:
        raise GovernedAIProviderConnectionError(
            "Choose enable or disable for the standby state.",
            reason_code="ai_provider_standby_action_invalid",
            status_code=422,
        )
    if not _CLIENT_REQUEST_ID.fullmatch(client_request_id.strip()):
        raise GovernedAIProviderConnectionError(
            "The standby request identifier is invalid.",
            reason_code="ai_provider_standby_request_invalid",
            status_code=422,
        )
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
    idempotency_key = _hash(
        {
            "organization_id": organization_id,
            "client_request_id": client_request_id.strip(),
        }
    )
    existing = (
        db.query(GovernedAIProviderStandbyEvent)
        .filter(
            GovernedAIProviderStandbyEvent.organization_id == organization_id,
            GovernedAIProviderStandbyEvent.idempotency_key == idempotency_key,
        )
        .one_or_none()
    )
    if existing is not None:
        expected_action = "enabled" if action == "enable" else "disabled"
        if existing.connection_id != connection_id or existing.action != expected_action:
            raise GovernedAIProviderConnectionError(
                "This standby request identifier was already used differently.",
                reason_code="ai_provider_standby_request_conflict",
                status_code=409,
            )
        return _result(db, existing, created=False)

    connection = (
        db.query(GovernedAIProviderConnection)
        .filter(
            GovernedAIProviderConnection.id == connection_id,
            GovernedAIProviderConnection.organization_id == organization_id,
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
    latest = _latest_org_event(db, organization_id=organization_id)
    if action == "disable":
        return _disable(
            db,
            connection=connection,
            latest=latest,
            actor_user_id=actor_user_id,
            idempotency_key=idempotency_key,
        )

    require_commercial_feature(
        db,
        organization_id=organization_id,
        feature_code=FEATURE_PRIVATE_AI_PROVIDER,
    )
    if (
        latest is not None
        and latest.action == "enabled"
        and _event_is_current(db, latest)
    ):
        if latest.connection_id == connection.id:
            raise GovernedAIProviderConnectionError(
                "This provider is already registered in zero-traffic standby.",
                reason_code="ai_provider_standby_already_enabled",
                status_code=409,
            )
        raise GovernedAIProviderConnectionError(
            "Disable the current standby provider before choosing another one.",
            reason_code="ai_provider_standby_another_enabled",
            status_code=409,
        )
    settings = settings_provider()
    if (
        str(getattr(settings, "ai_provider_backend", "")).strip().lower()
        != "mistral"
        or not str(getattr(settings, "mistral_api_key", "")).strip()
    ):
        raise GovernedAIProviderConnectionError(
            "The managed AI route must be configured before standby registration.",
            reason_code="ai_provider_managed_route_required",
            status_code=409,
        )
    normalized_acknowledgements = {
        key: acknowledgements.get(key) is True for key in STANDBY_ACKNOWLEDGEMENTS
    }
    if not all(normalized_acknowledgements.values()):
        raise GovernedAIProviderConnectionError(
            "Confirm every zero-traffic standby acknowledgement.",
            reason_code="ai_provider_standby_acknowledgement_required",
            status_code=422,
        )
    review = (
        db.query(GovernedAIProviderReview)
        .filter(
            GovernedAIProviderReview.id == review_id,
            GovernedAIProviderReview.organization_id == organization_id,
            GovernedAIProviderReview.connection_id == connection.id,
        )
        .one_or_none()
    )
    if review is None:
        raise GovernedAIProviderConnectionError(
            "An exact owner-approved benchmark review is required.",
            reason_code="ai_provider_standby_review_required",
            status_code=409,
        )
    benchmark = db.get(GovernedAIProviderBenchmark, review.benchmark_id)
    if (
        benchmark is None
        or benchmark.organization_id != organization_id
        or benchmark.connection_id != connection.id
        or review.decision != "approved_for_future_activation"
        or not provider_review_artifact_is_valid(review)
        or review.benchmark_artifact_hash != benchmark.artifact_hash
        or review.connection_evidence_hash != benchmark.connection_evidence_hash
    ):
        raise GovernedAIProviderConnectionError(
            "The saved owner review no longer matches the approved evidence.",
            reason_code="ai_provider_standby_review_integrity_failed",
            status_code=409,
        )
    require_exact_passing_evidence(
        db,
        connection=connection,
        benchmark=benchmark,
    )
    return _append_event(
        db,
        connection=connection,
        benchmark=benchmark,
        review=review,
        action="enabled",
        acknowledgements=normalized_acknowledgements,
        actor_user_id=actor_user_id,
        idempotency_key=idempotency_key,
        managed_route_configured=True,
    )


def _disable(
    db: Session,
    *,
    connection: GovernedAIProviderConnection,
    latest: GovernedAIProviderStandbyEvent | None,
    actor_user_id: str,
    idempotency_key: str,
) -> dict[str, object]:
    if (
        latest is None
        or latest.action != "enabled"
        or latest.connection_id != connection.id
    ):
        raise GovernedAIProviderConnectionError(
            "This provider is not currently registered in standby.",
            reason_code="ai_provider_standby_not_enabled",
            status_code=409,
        )
    benchmark = db.get(GovernedAIProviderBenchmark, latest.benchmark_id)
    review = db.get(GovernedAIProviderReview, latest.review_id)
    if benchmark is None or review is None:
        raise GovernedAIProviderConnectionError(
            "The standby evidence is unavailable. No routing change was made.",
            reason_code="ai_provider_standby_evidence_unavailable",
            status_code=409,
        )
    return _append_event(
        db,
        connection=connection,
        benchmark=benchmark,
        review=review,
        action="disabled",
        acknowledgements={"manual_disable_requested": True},
        actor_user_id=actor_user_id,
        idempotency_key=idempotency_key,
        managed_route_configured=_managed_route_is_configured(),
    )


def _append_event(
    db: Session,
    *,
    connection: GovernedAIProviderConnection,
    benchmark: GovernedAIProviderBenchmark,
    review: GovernedAIProviderReview,
    action: str,
    acknowledgements: dict[str, bool],
    actor_user_id: str,
    idempotency_key: str,
    managed_route_configured: bool,
) -> dict[str, object]:
    now = datetime.now(UTC)
    artifact = {
        "tenant_id": connection.organization_id,
        "organization_id": connection.organization_id,
        "connection_id": connection.id,
        "benchmark_id": benchmark.id,
        "review_id": review.id,
        "action": action,
        "managed_backend": "mistral",
        "routing_mode": "zero_traffic_standby",
        "traffic_percentage": 0,
        "customer_prompts_allowed": False,
        "automatic_changes_allowed": False,
        "automatic_activation_allowed": False,
        "benchmark_artifact_hash": benchmark.artifact_hash,
        "connection_evidence_hash": benchmark.connection_evidence_hash,
        "review_decision_hash": review.decision_hash,
        "acknowledgements": acknowledgements,
        "idempotency_key": idempotency_key,
        "created_by_user_id": actor_user_id,
        "created_at": now.isoformat(),
    }
    row = GovernedAIProviderStandbyEvent(
        tenant_id=connection.organization_id,
        organization_id=connection.organization_id,
        connection_id=connection.id,
        benchmark_id=benchmark.id,
        review_id=review.id,
        action=action,
        managed_backend="mistral",
        routing_mode="zero_traffic_standby",
        traffic_percentage=0,
        customer_prompts_allowed=False,
        automatic_changes_allowed=False,
        automatic_activation_allowed=False,
        benchmark_artifact_hash=benchmark.artifact_hash,
        connection_evidence_hash=benchmark.connection_evidence_hash,
        review_decision_hash=review.decision_hash,
        acknowledgements=acknowledgements,
        artifact_hash=_hash(artifact),
        idempotency_key=idempotency_key,
        created_by_user_id=actor_user_id,
        created_at=now,
    )
    db.add(row)
    db.flush()
    write_audit_log(
        db,
        tenant_id=connection.organization_id,
        actor_user_id=actor_user_id,
        event_type=f"ai.provider_standby.{action}",
        payload={
            "standby_event_id": row.id,
            "connection_id": connection.id,
            "review_id": review.id,
            "routing_mode": "zero_traffic_standby",
            "traffic_percentage": 0,
            "customer_prompts_allowed": False,
            "automatic_changes_allowed": False,
            "managed_route_unchanged": True,
        },
    )
    db.commit()
    db.refresh(row)
    return _result(
        db,
        row,
        created=True,
        managed_route_configured=managed_route_configured,
    )


def _latest_org_event(
    db: Session,
    *,
    organization_id: str,
) -> GovernedAIProviderStandbyEvent | None:
    return (
        db.query(GovernedAIProviderStandbyEvent)
        .filter(GovernedAIProviderStandbyEvent.organization_id == organization_id)
        .order_by(
            GovernedAIProviderStandbyEvent.created_at.desc(),
            GovernedAIProviderStandbyEvent.id.desc(),
        )
        .first()
    )


def current_provider_standby_event(
    db: Session,
    *,
    organization_id: str,
    connection: GovernedAIProviderConnection,
) -> GovernedAIProviderStandbyEvent | None:
    """Return the exact current zero-traffic event, never a stale registration."""
    latest = _latest_org_event(db, organization_id=organization_id)
    if (
        latest is None
        or latest.action != "enabled"
        or latest.connection_id != connection.id
        or not _event_is_current(db, latest, connection=connection)
    ):
        return None
    return latest


def _current_state(
    db: Session,
    *,
    organization_id: str,
    connection: GovernedAIProviderConnection,
    managed_route_configured: bool | None = None,
) -> dict[str, object]:
    latest = _latest_org_event(db, organization_id=organization_id)
    if managed_route_configured is None:
        managed_route_configured = _managed_route_is_configured()
    active_here = (
        latest is not None
        and latest.action == "enabled"
        and latest.connection_id == connection.id
        and _event_is_current(db, latest, connection=connection)
        and managed_route_configured
    )
    active_elsewhere = (
        latest is not None
        and latest.action == "enabled"
        and latest.connection_id != connection.id
        and _event_is_current(db, latest)
        and managed_route_configured
    )
    state = "standby" if active_here else "standby_elsewhere" if active_elsewhere else "inactive"
    evidence_current_here = (
        latest is not None
        and latest.action == "enabled"
        and latest.connection_id == connection.id
        and _event_is_current(db, latest, connection=connection)
    )
    summary = (
        "This provider is registered in zero-traffic standby. InsightOS managed AI remains the live route, and this provider receives no customer prompts."
        if active_here
        else "The standby record is preserved, but it is inactive until InsightOS managed AI is available again."
        if evidence_current_here and not managed_route_configured
        else "Another provider is registered in zero-traffic standby for this workspace."
        if active_elsewhere
        else "This provider is not registered in standby."
    )
    return {
        "state": state,
        "connection_id": latest.connection_id if active_elsewhere else connection.id,
        "event_id": latest.id if latest is not None else None,
        "summary": summary,
        "routing_mode": "zero_traffic_standby" if active_here else "inactive",
        "traffic_percentage": 0,
        "customer_prompts_allowed": False,
        "automatic_changes_allowed": False,
        "managed_route_unchanged": True,
        "managed_route_configured": managed_route_configured,
    }


def _event_is_current(
    db: Session,
    event: GovernedAIProviderStandbyEvent,
    *,
    connection: GovernedAIProviderConnection | None = None,
) -> bool:
    row = connection or db.get(GovernedAIProviderConnection, event.connection_id)
    return bool(
        row is not None
        and row.organization_id == event.organization_id
        and row.status == "candidate"
        and row.validation_status == "passed"
        and row.network_validation_status == "passed"
        and row.validation_evidence_hash
        and row.validation_evidence_hash == event.connection_evidence_hash
    )


def _managed_route_is_configured() -> bool:
    settings = get_settings()
    return bool(
        str(getattr(settings, "ai_provider_backend", "")).strip().lower()
        == "mistral"
        and str(getattr(settings, "mistral_api_key", "")).strip()
    )


def _serialize(row: GovernedAIProviderStandbyEvent) -> dict[str, object]:
    return {
        "id": row.id,
        "connection_id": row.connection_id,
        "benchmark_id": row.benchmark_id,
        "review_id": row.review_id,
        "action": row.action,
        "routing_mode": row.routing_mode,
        "traffic_percentage": 0,
        "customer_prompts_allowed": False,
        "automatic_changes_allowed": False,
        "automatic_activation_allowed": False,
        "created_at": row.created_at.isoformat(),
        "immutable": True,
    }


def _result(
    db: Session,
    row: GovernedAIProviderStandbyEvent,
    *,
    created: bool,
    managed_route_configured: bool | None = None,
) -> dict[str, object]:
    connection = db.get(GovernedAIProviderConnection, row.connection_id)
    if connection is None:
        raise GovernedAIProviderConnectionError(
            "Private AI provider not found.",
            reason_code="ai_provider_connection_not_found",
            status_code=404,
        )
    current = _current_state(
        db,
        organization_id=row.organization_id,
        connection=connection,
        managed_route_configured=managed_route_configured,
    )
    return {
        "created": created,
        "item": _serialize(row),
        "current": current,
        "truth": {"state": current["state"], "summary": current["summary"]},
        "managed_route": "mistral",
        "routing_enabled": False,
        "traffic_percentage": 0,
        "customer_prompts_allowed": False,
        "automatic_changes_allowed": False,
    }


def _hash(payload: dict[str, object]) -> str:
    return sha256(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()

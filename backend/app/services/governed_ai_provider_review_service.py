from __future__ import annotations

import json
from datetime import UTC, datetime
from hashlib import sha256

from sqlalchemy.orm import Session

from app.models.governed_ai_provider_benchmark import GovernedAIProviderBenchmark
from app.models.governed_ai_provider_connection import GovernedAIProviderConnection
from app.models.governed_ai_provider_review import GovernedAIProviderReview
from app.services.audit_service import write_audit_log
from app.services.commercial_plan_service import (
    FEATURE_PRIVATE_AI_PROVIDER,
    require_commercial_feature,
)
from app.services.governed_ai_provider_connection_service import (
    GovernedAIProviderConnectionError,
)
from app.services.governed_ai_provider_benchmark_service import (
    benchmark_artifact_is_valid,
)


APPROVAL_ACKNOWLEDGEMENTS = (
    "reviewed_synthetic_results",
    "understands_not_active",
    "understands_managed_fallback_required",
    "understands_no_automatic_changes",
)
SUPPORTED_DECISIONS = {"approved_for_future_activation", "rejected"}


def list_provider_reviews(
    db: Session,
    *,
    organization_id: str,
    connection_id: str,
) -> dict[str, object]:
    connection = (
        db.query(GovernedAIProviderConnection.id)
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
        db.query(GovernedAIProviderReview)
        .filter(
            GovernedAIProviderReview.organization_id == organization_id,
            GovernedAIProviderReview.connection_id == connection_id,
        )
        .order_by(
            GovernedAIProviderReview.reviewed_at.desc(),
            GovernedAIProviderReview.id.desc(),
        )
        .all()
    )
    return {
        "items": [_serialize(row) for row in rows],
        "count": len(rows),
        "truth": {
            "state": "human_decisions_only",
            "summary": (
                "These owner decisions are permanent records. They do not enable "
                "provider routing or authorize any automatic changes."
            ),
        },
        "routing_enabled": False,
        "automatic_activation_allowed": False,
    }


def review_provider_benchmark(
    db: Session,
    *,
    organization_id: str,
    connection_id: str,
    benchmark_id: str,
    actor_user_id: str,
    decision: str,
    acknowledgements: dict[str, bool],
) -> dict[str, object]:
    if decision not in SUPPORTED_DECISIONS:
        raise GovernedAIProviderConnectionError(
            "Choose a supported final review decision.",
            reason_code="ai_provider_review_decision_invalid",
            status_code=422,
        )
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
    benchmark = (
        db.query(GovernedAIProviderBenchmark)
        .filter(
            GovernedAIProviderBenchmark.id == benchmark_id,
            GovernedAIProviderBenchmark.organization_id == organization_id,
            GovernedAIProviderBenchmark.connection_id == connection_id,
        )
        .one_or_none()
    )
    if benchmark is None:
        raise GovernedAIProviderConnectionError(
            "Provider quality benchmark not found.",
            reason_code="ai_provider_benchmark_not_found",
            status_code=404,
        )

    normalized_acknowledgements = {
        key: acknowledgements.get(key) is True for key in APPROVAL_ACKNOWLEDGEMENTS
    }
    existing = (
        db.query(GovernedAIProviderReview)
        .filter(
            GovernedAIProviderReview.organization_id == organization_id,
            GovernedAIProviderReview.benchmark_id == benchmark.id,
        )
        .one_or_none()
    )
    if existing is not None:
        if (
            existing.decision != decision
            or existing.acknowledgements != normalized_acknowledgements
        ):
            raise GovernedAIProviderConnectionError(
                "This benchmark already has a different permanent owner decision.",
                reason_code="ai_provider_review_already_final",
                status_code=409,
        )
        return _result(existing, created=False)

    if decision == "approved_for_future_activation":
        require_commercial_feature(
            db,
            organization_id=organization_id,
            feature_code=FEATURE_PRIVATE_AI_PROVIDER,
        )

    if normalized_acknowledgements["reviewed_synthetic_results"] is not True:
        raise GovernedAIProviderConnectionError(
            "Confirm that you reviewed the synthetic benchmark results.",
            reason_code="ai_provider_review_acknowledgement_required",
            status_code=422,
        )
    if decision == "approved_for_future_activation":
        missing = [
            key
            for key in APPROVAL_ACKNOWLEDGEMENTS
            if normalized_acknowledgements[key] is not True
        ]
        if missing:
            raise GovernedAIProviderConnectionError(
                "Confirm every provider safety acknowledgement before approval.",
                reason_code="ai_provider_review_acknowledgement_required",
                status_code=422,
            )
        require_exact_passing_evidence(
            db,
            connection=connection,
            benchmark=benchmark,
        )

    reviewed_at = datetime.now(UTC)
    artifact = {
        "tenant_id": organization_id,
        "organization_id": organization_id,
        "connection_id": connection.id,
        "benchmark_id": benchmark.id,
        "benchmark_artifact_hash": benchmark.artifact_hash,
        "connection_evidence_hash": benchmark.connection_evidence_hash,
        "decision": decision,
        "acknowledgements": normalized_acknowledgements,
        "reviewed_by_user_id": actor_user_id,
        "reviewed_at": _iso_utc(reviewed_at),
    }
    row = GovernedAIProviderReview(
        tenant_id=organization_id,
        organization_id=organization_id,
        connection_id=connection.id,
        benchmark_id=benchmark.id,
        decision=decision,
        benchmark_artifact_hash=benchmark.artifact_hash,
        connection_evidence_hash=benchmark.connection_evidence_hash,
        acknowledgements=normalized_acknowledgements,
        decision_hash=_hash(artifact),
        automatic_activation_allowed=False,
        reviewed_by_user_id=actor_user_id,
        reviewed_at=reviewed_at,
    )
    db.add(row)
    db.flush()
    write_audit_log(
        db,
        tenant_id=organization_id,
        actor_user_id=actor_user_id,
        event_type="ai.provider_benchmark.reviewed",
        payload={
            "review_id": row.id,
            "connection_id": connection.id,
            "benchmark_id": benchmark.id,
            "decision": decision,
            "all_safety_acknowledgements_confirmed": (
                decision == "approved_for_future_activation"
            ),
            "routing_enabled": False,
            "automatic_activation_allowed": False,
        },
    )
    db.commit()
    db.refresh(row)
    return _result(row, created=True)


def require_exact_passing_evidence(
    db: Session,
    *,
    connection: GovernedAIProviderConnection,
    benchmark: GovernedAIProviderBenchmark,
) -> None:
    latest = (
        db.query(GovernedAIProviderBenchmark)
        .filter(
            GovernedAIProviderBenchmark.organization_id == connection.organization_id,
            GovernedAIProviderBenchmark.connection_id == connection.id,
        )
        .order_by(
            GovernedAIProviderBenchmark.created_at.desc(),
            GovernedAIProviderBenchmark.id.desc(),
        )
        .first()
    )
    if (
        latest is None
        or latest.id != benchmark.id
        or benchmark.status != "passed"
        or benchmark.case_count != 3
        or benchmark.passed_case_count != 3
    ):
        raise GovernedAIProviderConnectionError(
            "Approve only the latest benchmark after all three checks pass.",
            reason_code="ai_provider_review_passing_benchmark_required",
            status_code=409,
        )
    if not benchmark_artifact_is_valid(benchmark):
        raise GovernedAIProviderConnectionError(
            "The saved benchmark evidence could not be verified. Run a new benchmark.",
            reason_code="ai_provider_review_benchmark_integrity_failed",
            status_code=409,
        )
    if (
        connection.status != "candidate"
        or connection.validation_status != "passed"
        or connection.network_validation_status != "passed"
        or not connection.validation_evidence_hash
        or connection.validation_evidence_hash != benchmark.connection_evidence_hash
    ):
        raise GovernedAIProviderConnectionError(
            "Validate the provider again and run a new benchmark before approval.",
            reason_code="ai_provider_review_current_evidence_required",
            status_code=409,
        )


def provider_review_artifact_is_valid(row: GovernedAIProviderReview) -> bool:
    artifact = {
        "tenant_id": row.tenant_id,
        "organization_id": row.organization_id,
        "connection_id": row.connection_id,
        "benchmark_id": row.benchmark_id,
        "benchmark_artifact_hash": row.benchmark_artifact_hash,
        "connection_evidence_hash": row.connection_evidence_hash,
        "decision": row.decision,
        "acknowledgements": row.acknowledgements,
        "reviewed_by_user_id": row.reviewed_by_user_id,
        "reviewed_at": _iso_utc(row.reviewed_at),
    }
    return row.decision_hash == _hash(artifact)


def _hash(payload: dict[str, object]) -> str:
    return sha256(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()


def _iso_utc(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


def _serialize(row: GovernedAIProviderReview) -> dict[str, object]:
    approved = row.decision == "approved_for_future_activation"
    return {
        "id": row.id,
        "connection_id": row.connection_id,
        "benchmark_id": row.benchmark_id,
        "decision": row.decision,
        "acknowledgements": row.acknowledgements,
        "reviewed_at": row.reviewed_at.isoformat(),
        "immutable": True,
        "eligible_for_later_standby_activation": approved,
        "activation_status": "inactive",
        "routing_enabled": False,
        "automatic_activation_allowed": False,
        "automatic_changes_allowed": False,
    }


def _result(row: GovernedAIProviderReview, *, created: bool) -> dict[str, object]:
    approved = row.decision == "approved_for_future_activation"
    return {
        "created": created,
        "item": _serialize(row),
        "truth": {
            "state": (
                "eligible_for_later_standby_activation"
                if approved
                else "rejected"
            ),
            "summary": (
                "The owner review is recorded. A separate future activation step "
                "is still required, and the provider remains inactive."
                if approved
                else "The owner declined this benchmark. The provider remains inactive."
            ),
        },
        "managed_fallback_required": True,
        "routing_enabled": False,
        "automatic_activation_allowed": False,
    }

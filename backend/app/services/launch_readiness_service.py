from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.campaign import Campaign
from app.models.launch_readiness import LaunchReadinessDecision, LaunchReadinessProof
from app.models.provider_health import ProviderHealthState
from app.models.support import SupportRequest
from app.services import freshness_monitor_service, infra_service
from app.services.launch_experience_service import build_launch_experience_readiness
from app.services.production_capability_service import build_production_capability_matrix


PASS = "pass"
ATTENTION = "attention"
NEEDS_LIVE_PROOF = "needs_live_proof"
BLOCKER = "blocker"

ACTIVE_SUPPORT_STATUSES = {"received", "investigating", "waiting_for_customer", "escalated"}
PROVIDER_EVIDENCE_MAX_AGE = timedelta(hours=24)
PROOF_MAX_AGE = timedelta(days=7)
PROOF_MAX_VALIDITY = timedelta(days=45)
PROOF_SCHEMA_VERSION = "ops1-launch-proof-v1"
DECISION_SCHEMA_VERSION = "ops1-launch-decision-v1"

MANUAL_GATE_CONFIG = {
    "critical_journeys": {
        "category": "critical_journeys",
        "title": "Paid customer journeys",
        "proof_kind": "production_smoke",
        "summary": "Automated tests do not prove that the current production journeys work for a real owner.",
        "next_action": "Record current production smoke proof for onboarding, baseline, recommendation, report, billing, recovery, and sign-out.",
    },
    "recovery_drills": {
        "category": "recovery",
        "title": "Recovery and rollback drills",
        "proof_kind": "recovery_drill",
        "summary": "Recovery procedures require current operator evidence.",
        "next_action": "Run and timestamp billing, provider, WordPress, artifact, deployment rollback, and account-closure drills.",
    },
    "customer_communications": {
        "category": "support",
        "title": "Incident and status communication",
        "proof_kind": "communication_test",
        "summary": "A customer communication path and named incident owner still require live proof.",
        "next_action": "Verify the support inbox, status message path, escalation owner, and resolution template.",
    },
    "first_use_comprehension": {
        "category": "product_truth",
        "title": "Non-technical first-use proof",
        "proof_kind": "moderated_test",
        "summary": "Product completeness does not prove first-use comprehension.",
        "next_action": "Close the moderated five-participant launch test and attach the resolved confusion log.",
    },
    "known_limitations": {
        "category": "product_truth",
        "title": "Sales claims and known limitations",
        "proof_kind": "capability_review",
        "summary": "The final capability matrix and launch limitations require an operator review.",
        "next_action": "Confirm that sales, demos, pricing, and help copy describe only production-proven capabilities.",
    },
}

SENSITIVE_PROOF_PATTERN = re.compile(
    r"(?i)(https?://|bearer\s+|whsec_|sk_(?:live|test)_|xox[baprs]-|[A-Za-z0-9_-]{48,})"
)


class LaunchReadinessProofError(ValueError):
    def __init__(self, message: str, *, reason_code: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.status_code = status_code


def _item(
    *,
    code: str,
    category: str,
    title: str,
    state: str,
    summary: str,
    evidence: str,
    next_action: str,
    facts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "code": code,
        "category": category,
        "title": title,
        "state": state,
        "summary": summary,
        "evidence": evidence,
        "next_action": next_action,
        "facts": facts or {},
    }


def _runtime_gate() -> dict[str, Any]:
    settings = get_settings()
    missing: list[str] = []
    production_runtime = settings.app_env.strip().lower() == "production"
    tenant_isolation_enabled = bool(settings.database_rls_enabled)
    rate_limiting_enabled = bool(settings.rate_limit_enabled)
    rate_limit_store_connected = (
        infra_service.redis_connected() if rate_limiting_enabled else False
    )
    async_checks_performed = rate_limit_store_connected
    background_worker_active = (
        infra_service.worker_active() if async_checks_performed else False
    )
    scheduler_active = (
        infra_service.scheduler_active() if async_checks_performed else False
    )

    if not production_runtime:
        missing.append("production runtime")
    if not tenant_isolation_enabled:
        missing.append("database tenant isolation")
    if not rate_limiting_enabled:
        missing.append("request rate limiting")
    elif not rate_limit_store_connected:
        missing.append("request rate-limit storage")
    if async_checks_performed and not background_worker_active:
        missing.append("background worker heartbeat")
    if async_checks_performed and not scheduler_active:
        missing.append("scheduler heartbeat")

    facts = {
        "production_runtime": production_runtime,
        "database_tenant_isolation": tenant_isolation_enabled,
        "request_rate_limiting": rate_limiting_enabled,
        "rate_limit_store_connected": rate_limit_store_connected,
        "async_checks_performed": async_checks_performed,
        "background_worker_active": background_worker_active,
        "scheduler_active": scheduler_active,
    }

    if missing:
        return _item(
            code="production_runtime",
            category="security",
            title="Production safety configuration",
            state=BLOCKER,
            summary="Required production safeguards are not all active in this runtime.",
            evidence=(
                "Saved runtime configuration, the live rate-limit storage connection, "
                "and available worker heartbeats were checked without exposing secret values."
            ),
            next_action=f"Enable and verify: {', '.join(missing)}.",
            facts={**facts, "missing_count": len(missing)},
        )
    return _item(
        code="production_runtime",
        category="security",
        title="Production safety configuration",
        state=PASS,
        summary=(
            "The production runtime, tenant isolation, rate limiting, background worker, "
            "and scheduler are active."
        ),
        evidence=(
            "Saved runtime configuration, the live rate-limit storage connection, "
            "and worker heartbeats were checked without exposing secret values."
        ),
        next_action="Retain the deployment preflight and production smoke evidence for this release.",
        facts=facts,
    )


def _billing_gate() -> dict[str, Any]:
    settings = get_settings()
    configured = {
        "billing_provider": bool(settings.stripe_secret_key.strip()),
        "signed_webhooks": bool(settings.stripe_webhook_secret.strip()),
        "solo_price": bool(settings.stripe_price_solo.strip()),
        "growth_price": bool(settings.stripe_price_growth.strip()),
    }
    missing = [name for name, ready in configured.items() if not ready]
    state = PASS if not missing else BLOCKER
    return _item(
        code="billing_configuration",
        category="pricing",
        title="Paid plan configuration",
        state=state,
        summary=(
            "Checkout prices and signed billing webhooks are configured."
            if state == PASS
            else "The paid checkout configuration is incomplete."
        ),
        evidence="Only configuration presence was checked; the billing provider was not contacted.",
        next_action=(
            "Run a signed test-mode checkout, portal, renewal, failure, and cancellation proof."
            if state == PASS
            else "Configure the missing billing values, then run the signed billing lifecycle proof."
        ),
        facts={"configured_count": len(configured) - len(missing), "required_count": len(configured)},
    )


def _artifact_gate() -> dict[str, Any]:
    settings = get_settings()
    configured = all(
        value.strip()
        for value in (
            settings.object_storage_endpoint,
            settings.object_storage_bucket,
            settings.object_storage_access_key,
            settings.object_storage_secret_key,
        )
    )
    return _item(
        code="durable_artifacts",
        category="recovery",
        title="Durable report storage",
        state=PASS if configured else BLOCKER,
        summary=(
            "Durable report storage is configured."
            if configured
            else "Durable report storage is not fully configured."
        ),
        evidence="Only storage configuration presence was checked; no object was written or read.",
        next_action=(
            "Retain a production write, download, checksum, and restore proof for this release."
            if configured
            else "Configure durable object storage before accepting paid report delivery."
        ),
    )


def _provider_gate(db: Session, *, now: datetime) -> dict[str, Any]:
    rows = (
        db.query(ProviderHealthState)
        .filter(ProviderHealthState.environment == "production")
        .all()
    )
    if not rows:
        return _item(
            code="provider_health",
            category="provider_health",
            title="Production data-source health",
            state=NEEDS_LIVE_PROOF,
            summary="No production provider-health evidence has been saved yet.",
            evidence="The production provider-health ledger contains no rows.",
            next_action="Run the approved production smoke checks and save current provider evidence.",
            facts={"capability_count": 0},
        )

    unhealthy = [row for row in rows if row.breaker_state != "closed"]
    stale = [
        row
        for row in rows
        if row.updated_at is None or _as_utc(row.updated_at) < now - PROVIDER_EVIDENCE_MAX_AGE
    ]
    if unhealthy:
        state = BLOCKER
        summary = "At least one production data-source circuit is not closed."
        next_action = "Resolve or explicitly disable the affected capability before launch."
    elif len(stale) == len(rows):
        state = NEEDS_LIVE_PROOF
        summary = "Saved production provider evidence is too old to support a launch decision."
        next_action = "Refresh the approved production provider smoke checks."
    elif stale:
        state = ATTENTION
        summary = "Current provider evidence is healthy, but some capability evidence is stale."
        next_action = "Refresh the stale capability checks before the final go/no-go review."
    else:
        state = PASS
        summary = "All saved production provider circuits are closed and current."
        next_action = "Retain the provider-owned proof receipts and confirm quota before launch."

    return _item(
        code="provider_health",
        category="provider_health",
        title="Production data-source health",
        state=state,
        summary=summary,
        evidence="Saved circuit and freshness facts were checked; no provider network call was made.",
        next_action=next_action,
        facts={
            "capability_count": len(rows),
            "unhealthy_count": len(unhealthy),
            "stale_count": len(stale),
        },
    )


def _data_freshness_gate(db: Session) -> dict[str, Any]:
    active_campaign_count = (
        db.query(Campaign)
        .filter(Campaign.setup_state == "Active", Campaign.organization_id.isnot(None))
        .count()
    )
    if active_campaign_count == 0:
        return _item(
            code="data_freshness",
            category="data_freshness",
            title="Customer data freshness",
            state=NEEDS_LIVE_PROOF,
            summary="There is no active production-like customer scope to prove data freshness.",
            evidence="The active campaign inventory is empty.",
            next_action="Complete the maintained launch workspace and collect its first current data window.",
            facts={"active_campaign_count": 0},
        )

    freshness = freshness_monitor_service.get_data_freshness_summary(db)
    status = str(freshness.get("status") or "unknown")
    state = PASS
    if status == "stale":
        state = BLOCKER
    elif status != "healthy":
        state = ATTENTION
    return _item(
        code="data_freshness",
        category="data_freshness",
        title="Customer data freshness",
        state=state,
        summary={
            PASS: "Saved customer traffic facts are within the configured freshness window.",
            ATTENTION: "Customer traffic facts need a freshness review before launch.",
            BLOCKER: "At least one active customer scope has stale traffic facts.",
        }[state],
        evidence="The saved traffic-fact ledger was evaluated at the current configured threshold.",
        next_action=(
            "Retain the launch-workspace freshness screenshot and source receipts."
            if state == PASS
            else "Restore current collection and verify the affected customer scopes."
        ),
        facts={
            "active_campaign_count": active_campaign_count,
            "stale_campaign_count": int(freshness.get("stale_campaign_count") or 0),
            "max_staleness_days": int(freshness.get("max_staleness_days") or 0),
        },
    )


def _support_queue_gate(db: Session, *, now: datetime) -> dict[str, Any]:
    active_query = db.query(SupportRequest).filter(SupportRequest.status.in_(ACTIVE_SUPPORT_STATUSES))
    active_count = active_query.count()
    overdue_count = active_query.filter(SupportRequest.response_target_at < now).count()
    return _item(
        code="support_queue",
        category="support",
        title="Support response queue",
        state=BLOCKER if overdue_count else PASS,
        summary=(
            "One or more customer requests are beyond their response target."
            if overdue_count
            else "No open customer request is beyond its response target."
        ),
        evidence="Only request status and response-target timestamps were counted.",
        next_action=(
            "Assign and communicate on every overdue request before launch."
            if overdue_count
            else "Confirm the named on-call owner, hours, and escalation handoff."
        ),
        facts={"active_count": active_count, "overdue_count": overdue_count},
    )


def serialize_launch_readiness_proof(
    row: LaunchReadinessProof, *, now: datetime | None = None
) -> dict[str, Any]:
    evaluated = now or datetime.now(UTC)
    expires_at = _as_utc(row.expires_at)
    return {
        "id": row.id,
        "result": row.result,
        "proof_kind": row.proof_kind,
        "summary": row.summary,
        "evidence_reference": row.evidence_reference,
        "observed_at": _as_utc(row.observed_at).isoformat(),
        "expires_at": expires_at.isoformat(),
        "current": expires_at > evaluated,
    }


def _latest_manual_proofs(db: Session) -> dict[str, LaunchReadinessProof]:
    rows = (
        db.query(LaunchReadinessProof)
        .order_by(
            LaunchReadinessProof.observed_at.desc(),
            LaunchReadinessProof.created_at.desc(),
            LaunchReadinessProof.id.desc(),
        )
        .all()
    )
    latest: dict[str, LaunchReadinessProof] = {}
    for row in rows:
        latest.setdefault(row.gate_code, row)
    return latest


def _manual_gate(
    *,
    code: str,
    config: dict[str, str],
    proof: LaunchReadinessProof | None,
    now: datetime,
) -> dict[str, Any]:
    if proof is None:
        return _item(
            code=code,
            category=config["category"],
            title=config["title"],
            state=NEEDS_LIVE_PROOF,
            summary=config["summary"],
            evidence="This proof is intentionally not inferred from runtime configuration or unit tests.",
            next_action=config["next_action"],
        )

    serialized = serialize_launch_readiness_proof(proof, now=now)
    if not serialized["current"]:
        state = NEEDS_LIVE_PROOF
        summary = "The latest saved operator proof has expired."
        next_action = "Repeat the proof on the current production release and record a new receipt."
    elif proof.result == "failed":
        state = BLOCKER
        summary = proof.summary
        next_action = "Resolve the failed proof, repeat it, and append a passing receipt before launch."
    else:
        state = PASS
        summary = proof.summary
        next_action = "Repeat this proof before it expires or after a material contract change."

    item = _item(
        code=code,
        category=config["category"],
        title=config["title"],
        state=state,
        summary=summary,
        evidence="The latest append-only operator proof was evaluated by observed time and expiry.",
        next_action=next_action,
    )
    item["proof"] = serialized
    return item


def create_launch_readiness_proof(
    db: Session,
    *,
    gate_code: str,
    result: str,
    proof_kind: str,
    summary: str,
    evidence_reference: str,
    observed_at: datetime,
    expires_at: datetime,
    recorded_by_user_id: str,
    now: datetime | None = None,
) -> tuple[LaunchReadinessProof, bool]:
    evaluated = now or datetime.now(UTC)
    config = MANUAL_GATE_CONFIG.get(gate_code)
    if config is None:
        raise LaunchReadinessProofError(
            "This launch gate does not accept operator proof.",
            reason_code="launch_proof_gate_not_supported",
        )
    if result not in {"passed", "failed"}:
        raise LaunchReadinessProofError(
            "Choose whether the proof passed or failed.",
            reason_code="launch_proof_result_invalid",
        )
    if proof_kind != config["proof_kind"]:
        raise LaunchReadinessProofError(
            "The proof type does not match this launch gate.",
            reason_code="launch_proof_kind_mismatch",
        )

    clean_summary = " ".join(summary.split())
    clean_reference = " ".join(evidence_reference.split())
    if not 20 <= len(clean_summary) <= 300:
        raise LaunchReadinessProofError(
            "Summarize the production result in 20 to 300 characters.",
            reason_code="launch_proof_summary_invalid",
        )
    if not 8 <= len(clean_reference) <= 160:
        raise LaunchReadinessProofError(
            "Use a short internal evidence reference between 8 and 160 characters.",
            reason_code="launch_proof_reference_invalid",
        )
    if SENSITIVE_PROOF_PATTERN.search(clean_summary) or SENSITIVE_PROOF_PATTERN.search(
        clean_reference
    ):
        raise LaunchReadinessProofError(
            "Store an internal receipt reference, not a URL, credential, or token.",
            reason_code="launch_proof_sensitive_value_rejected",
        )

    observed = _as_utc(observed_at)
    expires = _as_utc(expires_at)
    if observed > evaluated + timedelta(minutes=5) or observed < evaluated - PROOF_MAX_AGE:
        raise LaunchReadinessProofError(
            "The proof must have been observed within the last seven days.",
            reason_code="launch_proof_observed_at_invalid",
        )
    if expires <= evaluated or expires <= observed or expires > observed + PROOF_MAX_VALIDITY:
        raise LaunchReadinessProofError(
            "The proof expiry must be after today and no more than 45 days after observation.",
            reason_code="launch_proof_expiry_invalid",
        )

    digest_payload = {
        "schema_version": PROOF_SCHEMA_VERSION,
        "gate_code": gate_code,
        "result": result,
        "proof_kind": proof_kind,
        "summary": clean_summary,
        "evidence_reference": clean_reference,
        "observed_at": observed.isoformat(),
        "expires_at": expires.isoformat(),
    }
    digest = hashlib.sha256(
        json.dumps(digest_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    existing = (
        db.query(LaunchReadinessProof)
        .filter(LaunchReadinessProof.evidence_digest == digest)
        .one_or_none()
    )
    if existing is not None:
        return existing, False

    row = LaunchReadinessProof(
        schema_version=PROOF_SCHEMA_VERSION,
        gate_code=gate_code,
        result=result,
        proof_kind=proof_kind,
        summary=clean_summary,
        evidence_reference=clean_reference,
        evidence_digest=digest,
        recorded_by_user_id=recorded_by_user_id,
        observed_at=observed,
        expires_at=expires,
        created_at=evaluated,
    )
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
    except IntegrityError:
        existing = (
            db.query(LaunchReadinessProof)
            .filter(LaunchReadinessProof.evidence_digest == digest)
            .one_or_none()
        )
        if existing is not None:
            return existing, False
        raise
    return row, True


def serialize_launch_readiness_decision(
    row: LaunchReadinessDecision, *, basis_digest: str
) -> dict[str, Any]:
    return {
        "id": row.id,
        "decision": row.decision,
        "release_reference": row.release_reference,
        "rationale": row.rationale,
        "basis_digest": row.basis_digest,
        "decided_by_user_id": row.decided_by_user_id,
        "created_at": _as_utc(row.created_at).isoformat(),
        "current": row.basis_digest == basis_digest,
        "acknowledgements": {
            "known_limitations": row.known_limitations_acknowledged,
            "support_owner": row.support_owner_confirmed,
            "rollback_owner": row.rollback_owner_confirmed,
            "evidence_current": row.evidence_current_confirmed,
        },
    }


def _decision_basis_digest(items: list[dict[str, Any]]) -> str:
    basis = [
        {
            "code": item["code"],
            "state": item["state"],
            "facts": item.get("facts") or {},
            "proof": item.get("proof"),
        }
        for item in items
    ]
    return hashlib.sha256(
        json.dumps(basis, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _latest_decision(db: Session) -> LaunchReadinessDecision | None:
    return (
        db.query(LaunchReadinessDecision)
        .order_by(
            LaunchReadinessDecision.created_at.desc(),
            LaunchReadinessDecision.id.desc(),
        )
        .first()
    )


def create_launch_readiness_decision(
    db: Session,
    *,
    decision: str,
    release_reference: str,
    rationale: str,
    known_limitations_acknowledged: bool,
    support_owner_confirmed: bool,
    rollback_owner_confirmed: bool,
    evidence_current_confirmed: bool,
    decided_by_user_id: str,
    now: datetime | None = None,
) -> tuple[LaunchReadinessDecision, bool]:
    evaluated = now or datetime.now(UTC)
    if decision not in {"go", "no_go"}:
        raise LaunchReadinessProofError(
            "Choose go or no go.",
            reason_code="launch_decision_invalid",
        )
    clean_reference = " ".join(release_reference.split())
    clean_rationale = " ".join(rationale.split())
    if not 8 <= len(clean_reference) <= 120:
        raise LaunchReadinessProofError(
            "Use a short internal release reference between 8 and 120 characters.",
            reason_code="launch_decision_reference_invalid",
        )
    if not 20 <= len(clean_rationale) <= 500:
        raise LaunchReadinessProofError(
            "Explain the decision in 20 to 500 characters.",
            reason_code="launch_decision_rationale_invalid",
        )
    if SENSITIVE_PROOF_PATTERN.search(clean_reference) or SENSITIVE_PROOF_PATTERN.search(
        clean_rationale
    ):
        raise LaunchReadinessProofError(
            "Store an internal decision reference, not a URL, credential, or token.",
            reason_code="launch_decision_sensitive_value_rejected",
        )
    if not evidence_current_confirmed:
        raise LaunchReadinessProofError(
            "Confirm that this decision uses the evidence currently shown on the board.",
            reason_code="launch_decision_evidence_not_confirmed",
            status_code=409,
        )

    readiness = build_launch_readiness(db, evaluated_at=evaluated)
    if decision == "go" and readiness["evidence_state"] != "ready":
        raise LaunchReadinessProofError(
            "A go decision requires every launch gate to have current passing evidence.",
            reason_code="launch_decision_evidence_not_ready",
            status_code=409,
        )
    if decision == "go" and not all(
        (
            known_limitations_acknowledged,
            support_owner_confirmed,
            rollback_owner_confirmed,
        )
    ):
        raise LaunchReadinessProofError(
            "A go decision requires the limitations, support owner, and rollback owner confirmations.",
            reason_code="launch_decision_acknowledgements_incomplete",
            status_code=409,
        )

    digest_payload = {
        "schema_version": DECISION_SCHEMA_VERSION,
        "decision": decision,
        "basis_digest": readiness["basis_digest"],
        "release_reference": clean_reference,
        "rationale": clean_rationale,
        "known_limitations_acknowledged": known_limitations_acknowledged,
        "support_owner_confirmed": support_owner_confirmed,
        "rollback_owner_confirmed": rollback_owner_confirmed,
        "evidence_current_confirmed": evidence_current_confirmed,
    }
    decision_digest = hashlib.sha256(
        json.dumps(digest_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    existing = (
        db.query(LaunchReadinessDecision)
        .filter(LaunchReadinessDecision.decision_digest == decision_digest)
        .one_or_none()
    )
    if existing is not None:
        return existing, False

    row = LaunchReadinessDecision(
        schema_version=DECISION_SCHEMA_VERSION,
        decision=decision,
        basis_digest=readiness["basis_digest"],
        release_reference=clean_reference,
        rationale=clean_rationale,
        known_limitations_acknowledged=known_limitations_acknowledged,
        support_owner_confirmed=support_owner_confirmed,
        rollback_owner_confirmed=rollback_owner_confirmed,
        evidence_current_confirmed=evidence_current_confirmed,
        decision_digest=decision_digest,
        decided_by_user_id=decided_by_user_id,
        created_at=evaluated,
    )
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
    except IntegrityError:
        existing = (
            db.query(LaunchReadinessDecision)
            .filter(LaunchReadinessDecision.decision_digest == decision_digest)
            .one_or_none()
        )
        if existing is not None:
            return existing, False
        raise
    return row, True


def build_launch_readiness(db: Session, *, evaluated_at: datetime | None = None) -> dict[str, Any]:
    now = evaluated_at or datetime.now(UTC)
    latest_proofs = _latest_manual_proofs(db)
    capability_matrix = build_production_capability_matrix(db, evaluated_at=now)
    experience = build_launch_experience_readiness(db, evaluated_at=now)
    items = [
        _runtime_gate(),
        _billing_gate(),
        _artifact_gate(),
        _provider_gate(db, now=now),
        _data_freshness_gate(db),
        _support_queue_gate(db, now=now),
        *[
            _manual_gate(
                code=code,
                config=config,
                proof=latest_proofs.get(code),
                now=now,
            )
            for code, config in MANUAL_GATE_CONFIG.items()
        ],
    ]
    limitations_gate = next(item for item in items if item["code"] == "known_limitations")
    limitations_gate["facts"] = {
        "catalog_capability_count": len(capability_matrix["capabilities"]),
        "production_proven_count": capability_matrix["counts"]["proven"],
        "limited_count": capability_matrix["counts"]["limited"],
        "unavailable_count": capability_matrix["counts"]["unavailable"],
        "missing_live_proof_count": capability_matrix["counts"]["needs_live_proof"],
        "stale_proof_count": capability_matrix["counts"]["stale"],
        "capability_basis_digest": capability_matrix["basis_digest"],
    }
    limitations_proof = latest_proofs.get("known_limitations")
    matrix_latest = capability_matrix.get("latest_observed_at")
    reviewed_after_matrix = bool(
        limitations_proof
        and matrix_latest
        and _as_utc(limitations_proof.observed_at) >= datetime.fromisoformat(matrix_latest)
    )
    if limitations_gate["state"] != BLOCKER and (
        capability_matrix["evidence_state"] != "ready"
        or (limitations_proof is not None and matrix_latest and not reviewed_after_matrix)
    ):
        limitations_gate["state"] = NEEDS_LIVE_PROOF
        limitations_gate["summary"] = (
            "The production capability matrix is incomplete or changed after the latest sales-claim review."
        )
        limitations_gate["evidence"] = (
            "Every marketed capability needs a current proven, limited, or unavailable receipt, "
            "followed by a sales-claim review of that exact matrix."
        )
        limitations_gate["next_action"] = (
            "Finish the capability matrix, publish every limitation, then repeat the sales-claim review."
        )

    journeys_gate = next(item for item in items if item["code"] == "critical_journeys")
    route_audit = experience["route_audit"]
    journeys_gate["facts"] = {
        "required_route_count": route_audit["required_route_count"],
        "required_viewport_count": route_audit["required_viewport_count"],
        "passed_route_count": route_audit["counts"]["passed"],
        "failed_route_count": route_audit["counts"]["failed"],
        "stale_route_count": route_audit["counts"]["stale"],
        "missing_route_count": route_audit["counts"]["missing"],
        "experience_basis_digest": experience["basis_digest"],
    }
    journeys_proof = latest_proofs.get("critical_journeys")
    route_latest = route_audit.get("latest_observed_at")
    journeys_reviewed_after = bool(
        journeys_proof
        and route_latest
        and _as_utc(journeys_proof.observed_at) >= datetime.fromisoformat(route_latest)
    )
    if route_audit["evidence_state"] == "blocked":
        journeys_gate["state"] = BLOCKER
        journeys_gate["summary"] = "At least one current desktop or mobile customer-route review failed."
        journeys_gate["evidence"] = (
            "Every primary customer route is reviewed separately on desktop and mobile, including loading, empty, error, and recovery behavior."
        )
        journeys_gate["next_action"] = (
            "Resolve every blocking route issue, repeat the failed reviews, then repeat the production journey proof."
        )
    elif journeys_gate["state"] != BLOCKER and (
        route_audit["evidence_state"] != "ready"
        or (journeys_proof is not None and route_latest and not journeys_reviewed_after)
    ):
        journeys_gate["state"] = NEEDS_LIVE_PROOF
        journeys_gate["summary"] = (
            "The desktop and mobile route audit is incomplete or changed after the latest journey proof."
        )
        journeys_gate["evidence"] = (
            "All primary customer routes need current desktop and mobile evidence before the final production journey receipt."
        )
        journeys_gate["next_action"] = (
            "Finish the route matrix, resolve its blockers, then repeat the paid customer journey proof."
        )

    first_use_gate = next(item for item in items if item["code"] == "first_use_comprehension")
    moderated = experience["moderated_sessions"]
    first_use_gate["facts"] = {
        "required_participant_count": moderated["counts"]["required"],
        "passed_participant_count": moderated["counts"]["passed"],
        "failed_participant_count": moderated["counts"]["failed"],
        "stale_participant_count": moderated["counts"]["stale"],
        "remaining_participant_count": moderated["counts"]["remaining"],
        "experience_basis_digest": experience["basis_digest"],
    }
    first_use_proof = latest_proofs.get("first_use_comprehension")
    session_latest = moderated.get("latest_observed_at")
    first_use_reviewed_after = bool(
        first_use_proof
        and session_latest
        and _as_utc(first_use_proof.observed_at) >= datetime.fromisoformat(session_latest)
    )
    if moderated["evidence_state"] == "blocked":
        first_use_gate["state"] = BLOCKER
        first_use_gate["summary"] = "At least one current non-technical moderated session failed."
        first_use_gate["evidence"] = (
            "Each participant completes the same first-use journey under an opaque reference; no personal details are stored."
        )
        first_use_gate["next_action"] = (
            "Resolve the participant's blocking confusion, repeat that session, then repeat the final moderated-test proof."
        )
    elif first_use_gate["state"] != BLOCKER and (
        moderated["evidence_state"] != "ready"
        or (first_use_proof is not None and session_latest and not first_use_reviewed_after)
    ):
        first_use_gate["state"] = NEEDS_LIVE_PROOF
        first_use_gate["summary"] = (
            "Five current non-technical moderated sessions are incomplete or changed after the latest first-use proof."
        )
        first_use_gate["evidence"] = (
            "Five distinct people must complete connection, baseline, next action, workflow, billing, and sign-out/revocation tasks without operator rescue."
        )
        first_use_gate["next_action"] = (
            "Complete five passing sessions, resolve the confusion log, then repeat the first-use proof."
        )

    counts = {
        state: sum(1 for item in items if item["state"] == state)
        for state in (PASS, ATTENTION, NEEDS_LIVE_PROOF, BLOCKER)
    }
    if counts[BLOCKER]:
        evidence_state = "blocked"
    elif counts[ATTENTION] or counts[NEEDS_LIVE_PROOF]:
        evidence_state = "incomplete"
    else:
        evidence_state = "ready"

    basis_digest = _decision_basis_digest(items)
    latest_decision_row = _latest_decision(db)
    latest_decision = (
        serialize_launch_readiness_decision(latest_decision_row, basis_digest=basis_digest)
        if latest_decision_row is not None
        else None
    )
    if latest_decision and latest_decision["current"]:
        overall_state = latest_decision["decision"]
        headline = (
            "A platform owner recorded go for the evidence currently shown."
            if overall_state == "go"
            else "A platform owner recorded no go for the evidence currently shown."
        )
    elif evidence_state == "blocked":
        overall_state = "no_go"
        headline = "Launch is blocked by current saved evidence."
    elif evidence_state == "incomplete":
        overall_state = "hold"
        headline = "No saved blocker is red, but required live launch proof is incomplete."
    else:
        overall_state = "ready_for_decision"
        headline = "Every gate has current passing evidence; a platform-owner decision is still required."

    return {
        "schema_version": "ops1-launch-readiness-v1",
        "evaluated_at": now.isoformat(),
        "evidence_state": evidence_state,
        "overall_state": overall_state,
        "headline": headline,
        "basis_digest": basis_digest,
        "latest_decision": latest_decision,
        "capability_matrix": {
            "evidence_state": capability_matrix["evidence_state"],
            "counts": capability_matrix["counts"],
            "basis_digest": capability_matrix["basis_digest"],
        },
        "launch_experience": {
            "evidence_state": experience["evidence_state"],
            "basis_digest": experience["basis_digest"],
            "route_counts": route_audit["counts"],
            "moderated_session_counts": moderated["counts"],
        },
        "counts": counts,
        "items": items,
        "limitations": [
            "This board does not contact Stripe, Google, automation tools, storage, or data providers.",
            "A passing automated gate cannot replace the required production-owned smoke receipt or moderated usability proof.",
            "No weighted readiness score is shown because unlike evidence must not be blended into a flattering number.",
        ],
    }


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)

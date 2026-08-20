from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.production_capability import ProductionCapabilityProof
from app.services.commercial_plan_service import FEATURES
from app.services.cost_economics_service import resolve_plan_economics


SCHEMA_VERSION = "ops1-production-capabilities-v1"
PROOF_SCHEMA_VERSION = "ops1-capability-proof-v1"
PROOF_MAX_AGE = timedelta(days=7)
PROOF_MAX_VALIDITY = timedelta(days=45)
PLAN_ORDER = ("solo", "multi_location", "enterprise")
RESULTS = {"proven", "limited", "unavailable"}
SENSITIVE_PATTERN = re.compile(
    r"(?i)(https?://|bearer\s+|traceback|stack trace|sqlalchemy|postgres|stripe|openai|"
    r"data[\s_-]*for[\s_-]*seo|google|microsoft|zapier|make\.com|n8n|"
    r"\b(?:provider|supplier|vendor)\b|whsec_|sk_(?:live|test)_|"
    r"xox[baprs]-|[A-Za-z0-9_-]{48,})"
)


class ProductionCapabilityError(ValueError):
    def __init__(self, message: str, *, reason_code: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.status_code = status_code


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _clean(value: str) -> str:
    return " ".join(value.strip().split())


def _capability_by_code(code: str):
    for feature in FEATURES:
        if feature.code == code:
            return feature
    return None


def _proof_digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def create_production_capability_proof(
    db: Session,
    *,
    capability_code: str,
    result: str,
    summary: str,
    customer_limitation: str | None,
    evidence_reference: str,
    observed_at: datetime,
    expires_at: datetime,
    recorded_by_user_id: str,
    now: datetime | None = None,
) -> tuple[ProductionCapabilityProof, bool]:
    evaluated = _as_utc(now or datetime.now(UTC))
    capability_code = capability_code.strip()
    result = result.strip().lower()
    summary = _clean(summary)
    limitation = _clean(customer_limitation or "")
    evidence_reference = _clean(evidence_reference)
    observed = _as_utc(observed_at)
    expires = _as_utc(expires_at)

    if _capability_by_code(capability_code) is None:
        raise ProductionCapabilityError(
            "This capability is not part of the maintained commercial catalog.",
            reason_code="production_capability_unknown",
        )
    if result not in RESULTS:
        raise ProductionCapabilityError(
            "Choose proven, limited, or unavailable.",
            reason_code="production_capability_result_invalid",
        )
    if not 20 <= len(summary) <= 300:
        raise ProductionCapabilityError(
            "Summarize the current production result in 20 to 300 characters.",
            reason_code="production_capability_summary_invalid",
        )
    if not 8 <= len(evidence_reference) <= 160:
        raise ProductionCapabilityError(
            "Use a short internal evidence reference between 8 and 160 characters.",
            reason_code="production_capability_reference_invalid",
        )
    if result in {"limited", "unavailable"} and not 20 <= len(limitation) <= 300:
        raise ProductionCapabilityError(
            "Limited and unavailable capabilities need a plain customer limitation.",
            reason_code="production_capability_limitation_required",
        )
    if result == "proven" and limitation:
        raise ProductionCapabilityError(
            "Use Limited when a customer-facing limitation still applies.",
            reason_code="production_capability_result_conflict",
        )
    if any(SENSITIVE_PATTERN.search(value) for value in (summary, limitation, evidence_reference)):
        raise ProductionCapabilityError(
            "Use internal receipt codes and customer-safe language without links, suppliers, or secrets.",
            reason_code="production_capability_sensitive_value_rejected",
        )
    if observed > evaluated + timedelta(minutes=5) or observed < evaluated - PROOF_MAX_AGE:
        raise ProductionCapabilityError(
            "The production result must have been observed within the last seven days.",
            reason_code="production_capability_observed_at_invalid",
        )
    if expires <= evaluated or expires <= observed or expires > observed + PROOF_MAX_VALIDITY:
        raise ProductionCapabilityError(
            "The recheck date must be after today and within 45 days of observation.",
            reason_code="production_capability_expiry_invalid",
        )

    digest_payload = {
        "schema_version": PROOF_SCHEMA_VERSION,
        "capability_code": capability_code,
        "result": result,
        "summary": summary,
        "customer_limitation": limitation or None,
        "evidence_reference": evidence_reference,
        "observed_at": observed.isoformat(),
        "expires_at": expires.isoformat(),
    }
    evidence_digest = _proof_digest(digest_payload)
    existing = (
        db.query(ProductionCapabilityProof)
        .filter(ProductionCapabilityProof.evidence_digest == evidence_digest)
        .one_or_none()
    )
    if existing is not None:
        return existing, False

    row = ProductionCapabilityProof(
        schema_version=PROOF_SCHEMA_VERSION,
        capability_code=capability_code,
        result=result,
        summary=summary,
        customer_limitation=limitation or None,
        evidence_reference=evidence_reference,
        evidence_digest=evidence_digest,
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
        exact = (
            db.query(ProductionCapabilityProof)
            .filter(ProductionCapabilityProof.evidence_digest == evidence_digest)
            .one_or_none()
        )
        if exact is not None:
            return exact, False
        raise
    return row, True


def serialize_production_capability_proof(
    row: ProductionCapabilityProof,
    *,
    now: datetime,
) -> dict[str, Any]:
    expires = _as_utc(row.expires_at)
    return {
        "id": row.id,
        "result": row.result,
        "summary": row.summary,
        "customer_limitation": row.customer_limitation,
        "evidence_reference": row.evidence_reference,
        "observed_at": _as_utc(row.observed_at).isoformat(),
        "expires_at": expires.isoformat(),
        "current": expires > now,
    }


def build_production_capability_matrix(
    db: Session,
    *,
    evaluated_at: datetime | None = None,
) -> dict[str, Any]:
    now = _as_utc(evaluated_at or datetime.now(UTC))
    rows = (
        db.query(ProductionCapabilityProof)
        .order_by(
            ProductionCapabilityProof.observed_at.desc(),
            ProductionCapabilityProof.created_at.desc(),
            ProductionCapabilityProof.id.desc(),
        )
        .all()
    )
    latest: dict[str, ProductionCapabilityProof] = {}
    for row in rows:
        latest.setdefault(row.capability_code, row)

    capabilities: list[dict[str, Any]] = []
    basis: list[dict[str, Any]] = []
    latest_observed: datetime | None = None
    for feature in FEATURES:
        proof = latest.get(feature.code)
        required_plan = resolve_plan_economics(feature.minimum_plan_code)
        minimum_index = PLAN_ORDER.index(required_plan.code)
        included_plans = [
            resolve_plan_economics(code).name for code in PLAN_ORDER[minimum_index:]
        ]
        if proof is None:
            claim_state = "needs_live_proof"
            proof_payload = None
        else:
            observed = _as_utc(proof.observed_at)
            latest_observed = max(latest_observed, observed) if latest_observed else observed
            proof_payload = serialize_production_capability_proof(proof, now=now)
            claim_state = proof.result if proof_payload["current"] else "stale"
        capabilities.append(
            {
                "code": feature.code,
                "label": feature.label,
                "summary": feature.summary,
                "minimum_plan": required_plan.name,
                "included_plans": included_plans,
                "claim_state": claim_state,
                "may_describe_as_available": claim_state == "proven",
                "must_show_limitation": claim_state in {"limited", "unavailable"},
                "proof": proof_payload,
            }
        )
        basis.append(
            {
                "code": feature.code,
                "claim_state": claim_state,
                "proof_id": proof.id if proof else None,
                "result": proof.result if proof else None,
                "customer_limitation": proof.customer_limitation if proof else None,
                "expires_at": _as_utc(proof.expires_at).isoformat() if proof else None,
            }
        )

    states = ("proven", "limited", "unavailable", "stale", "needs_live_proof")
    counts = {
        state: sum(1 for item in capabilities if item["claim_state"] == state)
        for state in states
    }
    basis_digest = _proof_digest(
        {"schema_version": SCHEMA_VERSION, "capabilities": basis}
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "catalog_version": "commercial-plans-2026-08-v3",
        "evaluated_at": now.isoformat(),
        "basis_digest": basis_digest,
        "evidence_state": (
            "ready"
            if counts["stale"] == 0 and counts["needs_live_proof"] == 0
            else "incomplete"
        ),
        "latest_observed_at": latest_observed.isoformat() if latest_observed else None,
        "counts": counts,
        "capabilities": capabilities,
        "limitations": [
            "Plan inclusion is not production proof.",
            "Limited and unavailable capabilities must remain visible in pricing, demos, help, and support copy.",
            "A current capability receipt does not replace the final sales-claim review or launch decision.",
        ],
    }

from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.governance.replay.hashing import build_hash, input_hash, output_hash, version_fingerprint
from app.models.intelligence import StrategyRecommendation
from app.models.strategy_execution_key import StrategyExecutionKey
from app.services.idempotency_service import (
    claim_pending_execution,
    get_or_create_execution,
    mark_execution_failed,
    persist_execution_result,
)
from app.services.strategy_engine.engine import build_campaign_strategy
from app.services.strategy_engine.profile import resolve_strategy_profile
from app.services.strategy_engine.schemas import CampaignStrategyOut, StrategyWindow
from app.services.strategy_engine.temporal_integration import integrate_temporal_state
from app.services.strategy_engine.thresholds import version_id as threshold_version

_REGISTRY_VERSION = "scenario-registry-v1"
_SIGNAL_SCHEMA_VERSION = "signals-v1"
_TERMINAL_RECOMMENDATION_STATUS = "ARCHIVED"


def build_campaign_strategy_idempotent(
    db: Session,
    *,
    tenant_id: str,
    campaign_id: str,
    window: StrategyWindow,
    raw_signals: dict[str, Any],
    tier: str,
) -> CampaignStrategyOut:
    request_payload = {
        "campaign_id": campaign_id,
        "window": {"date_from": window.date_from.isoformat(), "date_to": window.date_to.isoformat()},
        "raw_signals": raw_signals,
        "tier": tier,
    }
    in_hash = input_hash(request_payload)
    profile = resolve_strategy_profile(tier)
    profile_hash = profile.version_hash()
    version_tuple = {
        "engine_version": "phase2-controlled-scope",
        "threshold_bundle_version": threshold_version,
        "registry_version": _REGISTRY_VERSION,
        "signal_schema_version": _SIGNAL_SCHEMA_VERSION,
        "profile_version_hash": profile_hash,
    }
    version_hash = version_fingerprint(version_tuple)
    idem_key = f"{campaign_id}:{window.date_from.isoformat()}:{window.date_to.isoformat()}:{tier}"

    execution, _ = get_or_create_execution(
        db,
        tenant_id=tenant_id,
        campaign_id=campaign_id,
        operation_type="strategy_build",
        idempotency_key=idem_key,
        input_hash=in_hash,
        version_fingerprint=version_hash,
    )

    if execution.status == "completed" and execution.output_payload_json:
        payload = json.loads(execution.output_payload_json)
        return CampaignStrategyOut.model_validate(payload)

    if execution.status == "running":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Strategy build already running for this idempotency key")

    if execution.status == "failed":
        _reset_failed_to_pending(db, execution.id)

    claimed = claim_pending_execution(db, execution_id=execution.id)
    if claimed is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Strategy build execution is locked by another worker")

    try:
        output = build_campaign_strategy(
            campaign_id=campaign_id,
            window=window,
            raw_signals=raw_signals,
            tier=tier,
            db=db,
        )
        payload = output.model_dump(mode="json")
        temporal_visibility = integrate_temporal_state(
            db,
            campaign_id=campaign_id,
            window=window,
            profile=profile,
            payload=payload,
        )
        out_hash = output_hash(payload)
        payload["meta"]["threshold_bundle_version"] = threshold_version
        payload["meta"]["registry_version"] = _REGISTRY_VERSION
        payload["meta"]["signal_schema_version"] = _SIGNAL_SCHEMA_VERSION
        payload["meta"]["input_hash"] = in_hash
        payload["meta"]["output_hash"] = out_hash
        payload["meta"]["version_fingerprint"] = version_hash
        payload["meta"]["profile_version_hash"] = profile_hash
        payload["meta"]["build_hash"] = build_hash(input_digest=in_hash, output_digest=out_hash, version_digest=version_hash)
        if temporal_visibility is not None:
            payload["meta"]["temporal"] = temporal_visibility

        persist_execution_result(db, execution_id=execution.id, output_hash=out_hash, output_payload=payload)
        _persist_strategy_recommendation_metadata(
            db,
            tenant_id=tenant_id,
            campaign_id=campaign_id,
            idempotency_key=idem_key,
            input_hash=in_hash,
            output_hash=out_hash,
            version_tuple=version_tuple,
            build_hash_value=payload["meta"]["build_hash"],
        )

        return CampaignStrategyOut.model_validate(payload)
    except Exception as exc:
        mark_execution_failed(db, execution_id=execution.id, error_message=str(exc))
        raise


def _reset_failed_to_pending(db: Session, execution_id: str) -> None:
    from datetime import UTC, datetime

    row = db.get(StrategyExecutionKey, execution_id)
    if row is None or row.status != "failed":
        return
    row.status = "pending"
    row.updated_at = datetime.now(UTC)
    db.commit()


def _persist_strategy_recommendation_metadata(
    db: Session,
    *,
    tenant_id: str,
    campaign_id: str,
    idempotency_key: str,
    input_hash: str,
    output_hash: str,
    version_tuple: dict[str, str],
    build_hash_value: str,
) -> None:
    existing = (
        db.query(StrategyRecommendation)
        .filter(
            StrategyRecommendation.tenant_id == tenant_id,
            StrategyRecommendation.campaign_id == campaign_id,
            StrategyRecommendation.idempotency_key == idempotency_key,
        )
        .order_by(StrategyRecommendation.created_at.desc())
        .first()
    )

    payload = {
        "steps": [
            "rebuild_strategy_with_prior_tuple",
            "invalidate_conflicting_cached_payloads",
        ]
    }

    if existing is None:
        existing = StrategyRecommendation(
            tenant_id=tenant_id,
            campaign_id=campaign_id,
            recommendation_type="strategy_bundle_record",
            rationale="Deterministic strategy build artifact record",
            confidence=1.0,
            confidence_score=1.0,
            evidence_json=json.dumps(["deterministic_strategy_build"]),
            risk_tier=0,
            rollback_plan_json=json.dumps(payload),
            status=_TERMINAL_RECOMMENDATION_STATUS,
            idempotency_key=idempotency_key,
        )
        db.add(existing)

    existing.engine_version = version_tuple["engine_version"]
    existing.threshold_bundle_version = version_tuple["threshold_bundle_version"]
    existing.registry_version = version_tuple["registry_version"]
    existing.signal_schema_version = version_tuple["signal_schema_version"]
    existing.input_hash = input_hash
    existing.output_hash = output_hash
    existing.build_hash = build_hash_value
    db.commit()
